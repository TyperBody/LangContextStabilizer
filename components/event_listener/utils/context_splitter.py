"""上下文拆分器 - 将对话上下文拆分成块"""

import logging
from typing import List, Any

logger = logging.getLogger(__name__)


class ContextSplitter:
    """将对话上下文拆分成块"""
    
    def __init__(self, chunk_size: int = 5):
        """
        初始化上下文拆分器
        
        Args:
            chunk_size: 每个块包含的消息数
        """
        self.chunk_size = chunk_size
        logger.debug(f"上下文拆分器初始化，块大小: {chunk_size}")
    
    def split(self, messages: List[Any]) -> List[List[Any]]:
        """将消息列表拆分成块
        
        Args:
            messages: Message 对象列表
            
        Returns:
            块列表，每个块是Message列表
        """
        if not messages:
            logger.info(f"[ContextStabilizer] 拆分详情 | 输入为空，无需拆分")
            return []
        
        chunks = []
        for i in range(0, len(messages), self.chunk_size):
            chunk = messages[i:i + self.chunk_size]
            chunks.append(chunk)
        
        logger.info(f"[ContextStabilizer] 拆分详情 | 输入消息数: {len(messages)} | 块大小: {self.chunk_size} | 拆分结果: {len(chunks)} 段")
        for idx, chunk in enumerate(chunks):
            chunk_preview = self._get_chunk_preview(chunk)
            logger.info(f"[ContextStabilizer] 拆分详情 | 第 {idx+1}/{len(chunks)} 段 | 消息数: {len(chunk)} | 预览: \"{chunk_preview}\"")
        return chunks
    
    def merge(self, chunks: List[List[Any]]) -> List[Any]:
        """合并块为消息列表
        
        Args:
            chunks: 块列表
            
        Returns:
            合并后的消息列表
        """
        messages = []
        for chunk in chunks:
            messages.extend(chunk)
        
        logger.info(f"[ContextStabilizer] 合并详情 | 合并 {len(chunks)} 段 -> {len(messages)} 条消息")
        return messages
    
    def _get_chunk_preview(self, chunk: List[Any], max_length: int = 50) -> str:
        """获取块内容预览
        
        Args:
            chunk: 消息块
            max_length: 预览最大长度
            
        Returns:
            内容预览字符串
        """
        texts = []
        for msg in chunk:
            content = getattr(msg, 'content', '')
            if isinstance(content, list):
                for item in content:
                    if hasattr(item, 'text'):
                        texts.append(item.text)
                    elif isinstance(item, dict) and 'text' in item:
                        texts.append(item['text'])
            elif isinstance(content, str):
                texts.append(content)
        
        full_text = ' '.join(texts).replace('\n', ' ')
        if len(full_text) > max_length:
            return full_text[:max_length] + "..."
        return full_text
    
    def split_with_overlap(self, messages: List[Any], overlap: int = 1) -> List[List[Any]]:
        """带重叠的拆分，用于保持上下文连贯性
        
        Args:
            messages: Message 对象列表
            overlap: 重叠的消息数
            
        Returns:
            块列表，相邻块之间有overlap条消息重叠
        """
        if not messages:
            return []
        
        if overlap >= self.chunk_size:
            overlap = self.chunk_size - 1
        
        chunks = []
        step = self.chunk_size - overlap
        
        for i in range(0, len(messages), step):
            chunk = messages[i:i + self.chunk_size]
            if chunk:
                chunks.append(chunk)
            if i + self.chunk_size >= len(messages):
                break
        
        logger.debug(f"带重叠拆分：{len(messages)} 条消息 -> {len(chunks)} 个块，重叠: {overlap}")
        return chunks
