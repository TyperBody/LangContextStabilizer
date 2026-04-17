"""上下文压缩器 - 压缩上下文并注入原始 System Prompt"""

import logging
from typing import List, Any, Optional

from langbot_plugin.api.entities.builtin.provider import message as provider_message

logger = logging.getLogger(__name__)


class ContextCompressor:
    """压缩上下文并注入原始 System Prompt"""
    
    def __init__(
        self,
        plugin,
        model_uuid: str,
        target_length: int,
        compression_prompt: str,
        enable_prompt_injection: bool = True
    ):
        """
        初始化上下文压缩器
        
        Args:
            plugin: 插件实例，用于调用LLM
            model_uuid: 压缩模型的UUID
            target_length: 压缩后的目标消息数
            compression_prompt: 压缩提示词
            enable_prompt_injection: 是否启用Prompt注入
        """
        self.plugin = plugin
        self.model_uuid = model_uuid
        self.target_length = target_length
        self.compression_prompt = compression_prompt
        self.enable_prompt_injection = enable_prompt_injection
        logger.debug(f"上下文压缩器初始化，目标长度: {target_length}，Prompt注入: {enable_prompt_injection}")
    
    async def compress(self, messages: List[Any], original_prompt: str) -> List[Any]:
        """压缩上下文
        
        Args:
            messages: 原始消息列表
            original_prompt: 原始 System Prompt
            
        Returns:
            压缩后的消息列表
        """
        original_length = len(messages)
        
        if original_length <= self.target_length:
            logger.info(f"[ContextStabilizer] 压缩检查 | 消息数 {original_length} 不超过目标 {self.target_length}，无需压缩")
            return messages
        
        logger.info(f"[ContextStabilizer] 开始压缩 | 原消息数: {original_length} | 目标消息数: {self.target_length}")
        
        # 将消息转换为文本
        context_text = self._messages_to_text(messages)
        context_char_count = len(context_text)
        logger.info(f"[ContextStabilizer] 压缩输入 | 原文本长度: {context_char_count} 字符")
        
        # 构建压缩提示词
        prompt = self.compression_prompt.replace('{context}', context_text)
        
        # 调用LLM进行摘要 - 使用 Pydantic Message 对象
        llm_messages = [
            provider_message.Message(role="user", content=prompt)
        ]
        
        try:
            logger.info(f"[ContextStabilizer] 调用压缩模型 | 模型UUID: {self.model_uuid[:8]}...")
            response = await self.plugin.invoke_llm(
                llm_model_uuid=self.model_uuid,
                messages=llm_messages,
                funcs=[],
                extra_args={}
            )
            
            # 提取摘要内容
            summary_content = response.content if hasattr(response, 'content') else str(response)
            
            # 处理content可能是列表的情况
            if isinstance(summary_content, list):
                content_parts = []
                for item in summary_content:
                    if hasattr(item, 'text'):
                        content_parts.append(item.text)
                    elif isinstance(item, dict) and 'text' in item:
                        content_parts.append(item['text'])
                summary_content = ''.join(content_parts)
            
            summary_preview = summary_content[:100] + "..." if len(summary_content) > 100 else summary_content
            summary_preview = summary_preview.replace('\n', ' ')
            logger.info(f"[ContextStabilizer] 压缩摘要生成 | 摘要长度: {len(summary_content)} 字符 | 预览: \"{summary_preview}\"")
            
            # 构建压缩后的消息列表 - 使用字典格式
            compressed_messages = [
                self._create_message(
                    role="system",
                    content=f"[之前的对话摘要]\n{summary_content}"
                )
            ]
            
            # 保留最近的几条消息
            recent_count = min(self.target_length - 1, len(messages))
            if recent_count > 0:
                compressed_messages.extend(messages[-recent_count:])
            
            logger.info(f"[ContextStabilizer] 压缩完成 | 原长度: {original_length} -> 新长度: {len(compressed_messages)} | 保留最近消息: {recent_count} 条")
            return compressed_messages
            
        except Exception as e:
            logger.error(f"[ContextStabilizer] 压缩失败 | 错误: {e} | 使用简单截断策略")
            truncated = messages[-self.target_length:]
            logger.info(f"[ContextStabilizer] 截断完成 | 原长度: {original_length} -> 新长度: {len(truncated)}")
            return truncated
    
    def inject_original_prompt(self, messages: List[Any], original_prompt: str) -> List[Any]:
        """在压缩后的上下文中注入原始 System Prompt 提醒
        
        Args:
            messages: 消息列表
            original_prompt: 原始 System Prompt
            
        Returns:
            注入提醒后的消息列表
        """
        # 检查是否启用Prompt注入
        if not self.enable_prompt_injection:
            logger.info(f"[ContextStabilizer] Prompt注入已禁用，跳过注入")
            return messages
        
        reminder = self._create_message(
            role="system",
            content=f"[重要提醒] 请始终遵守以下设定：\n{original_prompt}"
        )
        
        prompt_preview = original_prompt[:50] + "..." if len(original_prompt) > 50 else original_prompt
        prompt_preview = prompt_preview.replace('\n', ' ')
        
        # 在第一条消息后插入提醒
        if len(messages) > 0:
            result = [messages[0], reminder] + list(messages[1:])
            logger.info(f"[ContextStabilizer] 注入提醒 | 原始Prompt已注入 | 提醒预览: \"{prompt_preview}\"")
            return result
        logger.info(f"[ContextStabilizer] 注入提醒 | 消息列表为空，仅添加提醒")
        return [reminder]
    
    def _create_message(self, role: str, content: str) -> provider_message.Message:
        """创建消息对象
        
        Args:
            role: 消息角色
            content: 消息内容
            
        Returns:
            Message 对象（Pydantic模型）
        """
        return provider_message.Message(role=role, content=content)
    
    def _messages_to_text(self, messages: List[Any]) -> str:
        """将消息列表转换为文本"""
        lines = []
        for msg in messages:
            role = getattr(msg, 'role', 'unknown')
            content = getattr(msg, 'content', '')
            
            # 处理content可能是列表的情况
            if isinstance(content, list):
                content_parts = []
                for item in content:
                    if hasattr(item, 'text'):
                        content_parts.append(item.text)
                    elif isinstance(item, dict) and 'text' in item:
                        content_parts.append(item['text'])
                content = ' '.join(content_parts)
            
            lines.append(f"[{role}]: {content}")
        return '\n'.join(lines)
