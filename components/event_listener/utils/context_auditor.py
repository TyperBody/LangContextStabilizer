"""上下文审计器 - 使用审查模型验证上下文"""

import asyncio
import json
import re
import logging
from dataclasses import dataclass
from typing import List, Any, Optional

from langbot_plugin.api.entities.builtin.provider import message as provider_message

logger = logging.getLogger(__name__)


@dataclass
class AuditResult:
    """审查结果"""
    passed: bool
    reason: str = ""
    chunk_index: int = -1
    timed_out: bool = False


class ContextAuditor:
    """使用审查模型验证上下文"""
    
    def __init__(self, plugin, model_uuid: str, timeout: int, system_prompt: str):
        """
        初始化上下文审计器
        
        Args:
            plugin: 插件实例，用于调用LLM
            model_uuid: 审查模型的UUID
            timeout: 审查超时时间（秒）
            system_prompt: 审查系统提示词
        """
        self.plugin = plugin
        self.model_uuid = model_uuid
        self.timeout = timeout
        self.system_prompt = system_prompt
        logger.debug(f"上下文审计器初始化，模型: {model_uuid}, 超时: {timeout}s")
    
    async def audit_chunk(self, chunk: List[Any], original_prompt: str, chunk_index: int, total_chunks: int = 0) -> AuditResult:
        """审查单个上下文块
        
        Args:
            chunk: Message 对象列表
            original_prompt: 原始 System Prompt
            chunk_index: 块索引
            total_chunks: 总块数（用于日志）
            
        Returns:
            AuditResult 对象
        """
        # 构建审查提示词
        audit_prompt = self.system_prompt.replace('{original_prompt}', original_prompt)
        
        # 将块转换为文本
        chunk_text = self._chunk_to_text(chunk)
        
        # 获取内容摘要用于日志
        content_preview = chunk_text[:50] + "..." if len(chunk_text) > 50 else chunk_text
        content_preview = content_preview.replace('\n', ' ')
        
        total_str = f"/{total_chunks}" if total_chunks > 0 else ""
        logger.info(f"[ContextStabilizer] 审查第 {chunk_index+1}{total_str} 段 | 内容摘要: \"{content_preview}\"")
        
        # 构建消息 - 使用 Pydantic Message 对象
        messages = [
            provider_message.Message(role="system", content=audit_prompt),
            provider_message.Message(role="user", content=f"请审查以下对话内容：\n\n{chunk_text}")
        ]
        
        try:
            # 带超时的LLM调用
            if self.timeout > 0:
                logger.info(f"[ContextStabilizer] 审查调用 | 第 {chunk_index+1} 段 | 超时限制: {self.timeout} 秒")
                response = await asyncio.wait_for(
                    self.plugin.invoke_llm(
                        llm_model_uuid=self.model_uuid,
                        messages=messages,
                        funcs=[],
                        extra_args={}
                    ),
                    timeout=self.timeout
                )
            else:
                response = await self.plugin.invoke_llm(
                    llm_model_uuid=self.model_uuid,
                    messages=messages,
                    funcs=[],
                    extra_args={}
                )
            
            # 解析响应
            result = self._parse_audit_response(response, chunk_index)
            status = "通过" if result.passed else "失败"
            logger.info(f"[ContextStabilizer] 审查结果 | 第 {chunk_index+1} 段: {status}" + (f" | 原因: {result.reason}" if result.reason else ""))
            return result
            
        except asyncio.TimeoutError:
            logger.warning(f"[ContextStabilizer] 审查超时 | 第 {chunk_index+1} 段 | 超时时间: {self.timeout} 秒")
            return AuditResult(
                passed=False,
                reason="Audit timed out",
                chunk_index=chunk_index,
                timed_out=True
            )
        except Exception as e:
            logger.error(f"[ContextStabilizer] 审查错误 | 第 {chunk_index+1} 段 | 错误: {e}")
            return AuditResult(
                passed=False,
                reason=f"Audit error: {str(e)}",
                chunk_index=chunk_index,
                timed_out=False
            )
    
    async def audit_all(self, chunks: List[List[Any]], original_prompt: str) -> List[AuditResult]:
        """审查所有上下文块
        
        Args:
            chunks: chunk列表，每个chunk是Message列表
            original_prompt: 原始 System Prompt
            
        Returns:
            AuditResult 对象列表
        """
        logger.info(f"[ContextStabilizer] 开始批量审查 | 总段数: {len(chunks)}")
        results = []
        
        for i, chunk in enumerate(chunks):
            result = await self.audit_chunk(chunk, original_prompt, i, len(chunks))
            results.append(result)
            
            # 记录结果但继续审查后续段
            if result.timed_out:
                logger.info(f"[ContextStabilizer] 第 {i+1} 段超时，继续审查下一段")
            elif not result.passed:
                logger.info(f"[ContextStabilizer] 第 {i+1} 段审查失败，继续审查下一段")
        
        passed_count = sum(1 for r in results if r.passed and not r.timed_out)
        timeout_count = sum(1 for r in results if r.timed_out)
        failed_count = sum(1 for r in results if not r.passed and not r.timed_out)
        logger.info(f"[ContextStabilizer] 批量审查完成 | 通过: {passed_count} | 失败: {failed_count} | 超时: {timeout_count} | 总计: {len(chunks)}")
        return results
    
    def _chunk_to_text(self, chunk: List[Any]) -> str:
        """将消息块转换为文本"""
        lines = []
        for msg in chunk:
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
    
    def _parse_audit_response(self, response, chunk_index: int) -> AuditResult:
        """解析审查模型的响应"""
        try:
            # 获取响应内容
            content = response.content if hasattr(response, 'content') else str(response)
            
            # 处理content可能是列表的情况
            if isinstance(content, list):
                content_parts = []
                for item in content:
                    if hasattr(item, 'text'):
                        content_parts.append(item.text)
                    elif isinstance(item, dict) and 'text' in item:
                        content_parts.append(item['text'])
                content = ''.join(content_parts)
            
            # 尝试解析 JSON
            json_match = re.search(r'\{[^{}]*\}', content)
            if json_match:
                result = json.loads(json_match.group())
                return AuditResult(
                    passed=result.get('pass', True),
                    reason=result.get('reason', ''),
                    chunk_index=chunk_index
                )
            
            # 如果没有 JSON，尝试简单判断
            content_lower = content.lower()
            if 'pass' in content_lower and 'false' in content_lower:
                return AuditResult(passed=False, reason=content, chunk_index=chunk_index)
            elif 'pass' in content_lower and 'true' in content_lower:
                return AuditResult(passed=True, chunk_index=chunk_index)
            
            # 默认通过
            return AuditResult(passed=True, chunk_index=chunk_index)
            
        except Exception as e:
            logger.warning(f"解析审查响应失败: {e}")
            return AuditResult(
                passed=True,  # 解析失败默认通过
                reason=f"Parse error: {str(e)}",
                chunk_index=chunk_index
            )
