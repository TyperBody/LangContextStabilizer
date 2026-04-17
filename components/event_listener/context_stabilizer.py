"""上下文稳定器事件监听器 - 监听流水线事件，执行上下文审查逻辑"""
from __future__ import annotations

import logging
import time
from typing import List, Any

from langbot_plugin.api.definition.components.common.event_listener import EventListener
from langbot_plugin.api.entities import events, context

from .utils.frequency_counter import FrequencyCounter
from .utils.steganography_detector import SteganographyDetector
from .utils.context_splitter import ContextSplitter
from .utils.context_auditor import ContextAuditor
from .utils.context_compressor import ContextCompressor

logger = logging.getLogger(__name__)


class ContextStabilizerListener(EventListener):
    """上下文稳定器事件监听器"""
    
    def __init__(self):
        super().__init__()
        
        # 注册事件处理器
        @self.handler(events.PromptPreProcessing)
        async def on_prompt_preprocessing(event_context: context.EventContext):
            await self._handle_prompt_preprocessing(event_context)
        
        @self.handler(events.NormalMessageResponded)
        async def on_message_responded(event_context: context.EventContext):
            await self._handle_message_responded(event_context)
    
    async def initialize(self):
        """初始化事件监听器"""
        # 获取配置
        self.config = self.plugin.get_config()
        
        # 初始化各子组件
        self.frequency_counter = FrequencyCounter(
            plugin=self.plugin,
            frequency=self.config.get('audit_frequency', 3)
        )
        
        # 解析隐写检测模式
        steganography_patterns_str = self.config.get('steganography_patterns', '')
        steganography_patterns = [
            p.strip() for p in steganography_patterns_str.split('\n') 
            if p.strip()
        ] if steganography_patterns_str else None
        
        self.steganography_detector = SteganographyDetector(
            patterns=steganography_patterns
        )
        
        self.context_splitter = ContextSplitter(
            chunk_size=self.config.get('chunk_size', 5)
        )
        
        self.context_auditor = ContextAuditor(
            plugin=self.plugin,
            model_uuid=self.config.get('audit_model_uuid', ''),
            timeout=self.config.get('audit_timeout_seconds', 10),
            system_prompt=self.config.get('audit_system_prompt', '')
        )
        
        # 压缩模型：如果未配置则使用审查模型
        compression_model = self.config.get('compression_model_uuid') or self.config.get('audit_model_uuid', '')
        
        self.context_compressor = ContextCompressor(
            plugin=self.plugin,
            model_uuid=compression_model,
            target_length=self.config.get('compress_target_length', 5),
            compression_prompt=self.config.get('compression_prompt', ''),
            enable_prompt_injection=self.config.get('enable_prompt_injection', True)
        )
        
        # 动态频率配置
        self.enable_adaptive_frequency = self.config.get('enable_adaptive_frequency', False)
        self.frequency_increase_step = self.config.get('frequency_increase_step', 1)
        self.frequency_recovery_threshold = self.config.get('frequency_recovery_threshold', 3)
        self.min_audit_frequency = self.config.get('min_audit_frequency', 1)
        
        if self.enable_adaptive_frequency:
            logger.info(
                f"[ContextStabilizer] 动态频率已启用 | 增加步长: {self.frequency_increase_step} | "
                f"恢复阈值: {self.frequency_recovery_threshold} | 最小间隔: {self.min_audit_frequency}"
            )
        
        logger.info("上下文稳定器事件监听器初始化完成")
    
    async def _handle_prompt_preprocessing(self, event_context: context.EventContext):
        """处理 PromptPreProcessing 事件"""
        start_time = time.time()
        event = event_context.event
        session_name = event.session_name
        
        # 获取原始 System Prompt 和对话历史
        default_prompt = event.default_prompt  # list[Message | MessageChunk]
        prompt = event.prompt  # list[Message | MessageChunk]
        original_length = len(prompt)
        
        # 开始处理日志
        logger.info(f"[ContextStabilizer] 开始处理上下文 | 会话: {session_name} | 上下文长度: {original_length} 条消息")
        
        # 提取原始 System Prompt 文本
        original_system_prompt = self._extract_system_prompt_text(default_prompt)
        
        # 检查是否需要强制压缩（上下文过长）
        max_context_length = self.config.get('max_context_length', 20)
        if len(prompt) > max_context_length:
            logger.info(f"[ContextStabilizer] 压缩触发 | 原因: 长度超限 ({len(prompt)} > {max_context_length})")
            compressed = await self.context_compressor.compress(prompt, original_system_prompt)
            compressed = self.context_compressor.inject_original_prompt(compressed, original_system_prompt)
            logger.info(f"[ContextStabilizer] 上下文写入 | 修改了 {len(compressed)} 条消息")
            event.prompt = compressed
            
            # 破例审查：上下文超限压缩后立即执行审查（不受频率限制）
            if self.config.get('audit_model_uuid'):
                logger.info(f"[ContextStabilizer] 破例审查 | 原因: 上下文超限压缩后")
                
                # 拆分上下文
                chunks = self.context_splitter.split(compressed)
                logger.info(f"[ContextStabilizer] 上下文拆分 | 总共拆分为 {len(chunks)} 段")
                
                # 审查各块
                audit_results = await self.context_auditor.audit_all(chunks, original_system_prompt)
                
                # 处理审查结果（破例审查不触发再次压缩，只移除问题段）
                processed_chunks = []
                for i, result in enumerate(audit_results):
                    if result.timed_out:
                        logger.info(f"[ContextStabilizer] 审查结果 | 第 {i+1} 段: 超时")
                        # 破例审查中，超时段按移除处理
                        continue
                    elif not result.passed:
                        logger.info(f"[ContextStabilizer] 审查结果 | 第 {i+1} 段: 失败 | 原因: {result.reason}")
                        continue
                    else:
                        logger.info(f"[ContextStabilizer] 审查结果 | 第 {i+1} 段: 通过")
                        processed_chunks.append(chunks[i])
                
                # 合并通过审查的块
                merged = self.context_splitter.merge(processed_chunks)
                logger.info(f"[ContextStabilizer] 上下文写入 | 修改了 {len(merged)} 条消息")
                event.prompt = merged
            
            elapsed = time.time() - start_time
            logger.info(f"[ContextStabilizer] 处理完成 | 总耗时: {elapsed:.2f} 秒")
            return
        
        # 检查是否达到审查周期
        current_count = await self.frequency_counter.get_count(session_name)
        base_audit_frequency = self.config.get('audit_frequency', 3)
        
        # 根据是否启用动态频率选择不同的检查方法
        if self.enable_adaptive_frequency:
            current_frequency = await self.frequency_counter.get_current_frequency(session_name, base_audit_frequency)
            should_audit = await self.frequency_counter.should_audit_adaptive(session_name, base_audit_frequency)
            logger.info(
                f"[ContextStabilizer] 频率检查 | 当前计数: {current_count}/{current_frequency} (动态) | "
                f"基础频率: {base_audit_frequency} | 本轮是否审查: {'是' if should_audit else '否'}"
            )
        else:
            should_audit = await self.frequency_counter.should_audit(session_name)
            logger.info(
                f"[ContextStabilizer] 频率检查 | 当前计数: {current_count}/{base_audit_frequency} | "
                f"本轮是否审查: {'是' if should_audit else '否'}"
            )
        
        if not should_audit:
            await self.frequency_counter.increment(session_name)
            elapsed = time.time() - start_time
            logger.info(f"[ContextStabilizer] 处理完成 | 总耗时: {elapsed:.2f} 秒")
            return
        
        # 重置计数器
        await self.frequency_counter.reset(session_name)
        
        # 隐写检测
        if self.config.get('enable_steganography_detection', True):
            context_text = self._messages_to_text(prompt)
            has_steganography = self.steganography_detector.detect(context_text)
            logger.info(f"[ContextStabilizer] 隐写检测 | 检测到隐写字符: {'是' if has_steganography else '否'}")
            
            if has_steganography:
                # 获取检测报告
                report = self.steganography_detector.get_detection_report(context_text)
                logger.warning(f"[ContextStabilizer] 隐写检测详情 | 字符编码: {report['char_codes']}")
                logger.info(f"[ContextStabilizer] 压缩触发 | 原因: 隐写检测")
                
                compressed = await self.context_compressor.compress(prompt, original_system_prompt)
                compressed = self.context_compressor.inject_original_prompt(compressed, original_system_prompt)
                logger.info(f"[ContextStabilizer] 上下文写入 | 修改了 {len(compressed)} 条消息")
                event.prompt = compressed
                elapsed = time.time() - start_time
                logger.info(f"[ContextStabilizer] 处理完成 | 总耗时: {elapsed:.2f} 秒")
                return
        else:
            logger.info(f"[ContextStabilizer] 隐写检测 | 检测已禁用")
        
        # 检查审查模型是否配置
        if not self.config.get('audit_model_uuid'):
            logger.warning(f"[ContextStabilizer] 审查模型未配置，跳过审查")
            elapsed = time.time() - start_time
            logger.info(f"[ContextStabilizer] 处理完成 | 总耗时: {elapsed:.2f} 秒")
            return
        
        # 拆分上下文
        chunks = self.context_splitter.split(prompt)
        logger.info(f"[ContextStabilizer] 上下文拆分 | 总共拆分为 {len(chunks)} 段")
        
        # 审查各块
        audit_results = await self.context_auditor.audit_all(chunks, original_system_prompt)
        
        # 处理审查结果
        processed_chunks = []
        passed_chunk_indices = []
        failed_chunks = []
        timeout_chunks = []
        timeout_action = self.config.get('timeout_action', 'remove_chunk')
        
        for i, result in enumerate(audit_results):
            if result.timed_out:
                timeout_chunks.append(i)
                logger.info(f"[ContextStabilizer] 审查结果 | 第 {i+1} 段: 超时")
                
                # 超时处理：根据配置决定是否保留该段
                if timeout_action == 'remove_chunk':
                    # 跳过这个块（不添加到processed_chunks）
                    continue
                # compress_all 策略会在后面统一处理
                
            elif not result.passed:
                failed_chunks.append(i)
                logger.info(f"[ContextStabilizer] 审查结果 | 第 {i+1} 段: 失败 | 原因: {result.reason}")
                # 审查失败：跳过该段，继续处理其他段
                continue
            else:
                logger.info(f"[ContextStabilizer] 审查结果 | 第 {i+1} 段: 通过")
                processed_chunks.append(chunks[i])
                passed_chunk_indices.append(i)
        
        # 计算移除的消息数
        removed_message_count = 0
        for i in failed_chunks:
            removed_message_count += len(chunks[i])
        for i in timeout_chunks:
            if timeout_action == 'remove_chunk':
                removed_message_count += len(chunks[i])
        
        # 计算保留的消息数
        retained_message_count = sum(len(chunk) for chunk in processed_chunks)
        
        # 判断审查整体是否通过（用于动态频率调整）
        audit_passed = len(failed_chunks) == 0 and len(timeout_chunks) == 0
        
        # 动态频率调整
        if self.enable_adaptive_frequency:
            base_audit_frequency = self.config.get('audit_frequency', 3)
            adjustment_result = await self.frequency_counter.record_audit_result(
                session_name=session_name,
                passed=audit_passed,
                base_frequency=base_audit_frequency,
                frequency_increase_step=self.frequency_increase_step,
                frequency_recovery_threshold=self.frequency_recovery_threshold,
                min_audit_frequency=self.min_audit_frequency
            )
            
            if adjustment_result['adjusted']:
                logger.info(
                    f"[ContextStabilizer] 动态频率变更 | 会话: {session_name} | "
                    f"审查结果: {'通过' if audit_passed else '失败'} | "
                    f"频率: {adjustment_result['old_frequency']} -> {adjustment_result['new_frequency']}"
                )
        
        # 处理统计日志
        if timeout_chunks:
            strategy = 'skip' if timeout_action == 'remove_chunk' else 'compress_all'
            timeout_removed = sum(len(chunks[i]) for i in timeout_chunks) if timeout_action == 'remove_chunk' else 0
            logger.info(f"[ContextStabilizer] 超时处理 | 策略: {strategy} | 受影响段数: {len(timeout_chunks)} | 段索引: {[i+1 for i in timeout_chunks]} | 移除消息数: {timeout_removed}")
        
        if failed_chunks:
            failed_removed = sum(len(chunks[i]) for i in failed_chunks)
            logger.info(f"[ContextStabilizer] 移除失败段 | 段索引: {[i+1 for i in failed_chunks]} | 移除消息数: {failed_removed}")
        
        if passed_chunk_indices:
            logger.info(f"[ContextStabilizer] 保留通过段 | 段索引: {[i+1 for i in passed_chunk_indices]} | 保留消息数: {retained_message_count}")
        
        # 判断是否需要压缩全部上下文
        need_compression = False
        compression_reason = ""
        
        # 如果超时策略是 compress_all 且有超时的段
        if timeout_action == 'compress_all' and timeout_chunks:
            need_compression = True
            compression_reason = f"审查超时（{len(timeout_chunks)} 段）"
        
        if need_compression:
            logger.info(f"[ContextStabilizer] 压缩触发 | 原因: {compression_reason}")
            compressed = await self.context_compressor.compress(prompt, original_system_prompt)
            compressed = self.context_compressor.inject_original_prompt(compressed, original_system_prompt)
            logger.info(f"[ContextStabilizer] 压缩完成 | 原长度: {original_length} -> 新长度: {len(compressed)}")
            logger.info(f"[ContextStabilizer] 上下文写入 | 修改了 {len(compressed)} 条消息")
            event.prompt = compressed
        else:
            # 合并通过审查的块
            merged = self.context_splitter.merge(processed_chunks)
            logger.info(f"[ContextStabilizer] 上下文写入 | 修改了 {len(merged)} 条消息")
            event.prompt = merged
        
        elapsed = time.time() - start_time
        logger.info(f"[ContextStabilizer] 处理完成 | 总耗时: {elapsed:.2f} 秒")
    
    async def _handle_message_responded(self, event_context: context.EventContext):
        """处理 NormalMessageResponded 事件（用于统计）"""
        event = event_context.event
        session_name = f"{event.launcher_type}_{event.launcher_id}"
        response_len = len(event.response_text) if hasattr(event, 'response_text') else 0
        
        logger.info(f"[ContextStabilizer] 消息响应完成 | 会话: {session_name} | 回复长度: {response_len}")
    
    def _extract_system_prompt_text(self, default_prompt: List[Any]) -> str:
        """从 default_prompt 中提取文本"""
        texts = []
        for msg in default_prompt:
            content = getattr(msg, 'content', None)
            if content is None:
                continue
            
            if isinstance(content, str):
                texts.append(content)
            elif isinstance(content, list):
                for item in content:
                    if hasattr(item, 'text'):
                        texts.append(item.text)
                    elif isinstance(item, dict) and 'text' in item:
                        texts.append(item['text'])
        return '\n'.join(texts)
    
    def _messages_to_text(self, messages: List[Any]) -> str:
        """将消息列表转换为纯文本"""
        texts = []
        for msg in messages:
            content = getattr(msg, 'content', None)
            if content is None:
                continue
            
            if isinstance(content, str):
                texts.append(content)
            elif isinstance(content, list):
                for item in content:
                    if hasattr(item, 'text'):
                        texts.append(item.text)
                    elif isinstance(item, dict) and 'text' in item:
                        texts.append(item['text'])
        return '\n'.join(texts)
