"""隐写检测器 - 检测文本中的隐写字符"""

import re
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


class SteganographyDetector:
    """检测文本中的隐写字符"""
    
    # 默认隐写字符模式
    DEFAULT_PATTERNS = [
        r'[\u200b-\u200f]',  # 零宽字符 (零宽空格、零宽不连字等)
        r'[\u2060-\u206f]',  # 不可见格式字符
        r'[\ufeff]',         # BOM字符
        r'[\u00ad]',         # 软连字符
        r'[\u034f]',         # 组合字形连接符
        r'[\u180e]',         # 蒙古语元音分隔符
        r'[\u2000-\u200a]',  # 各种空格
        r'[\u3000]',         # 全角空格
        r'[\u115f\u1160]',   # 韩语填充字符
        r'[\uffa0]',         # 半角韩语填充字符
    ]
    
    def __init__(self, patterns: Optional[List[str]] = None):
        """
        初始化隐写检测器
        
        Args:
            patterns: 正则表达式模式列表，每个模式用于匹配隐写字符
        """
        self.patterns = []
        pattern_list = patterns if patterns else self.DEFAULT_PATTERNS
        
        for p in pattern_list:
            if isinstance(p, str):
                p = p.strip()
                if p:
                    try:
                        self.patterns.append(re.compile(p))
                    except re.error as e:
                        logger.warning(f"无效的正则表达式模式 '{p}': {e}")
        
        logger.debug(f"隐写检测器初始化，加载了 {len(self.patterns)} 个检测模式")
    
    def detect(self, text: str) -> bool:
        """检测文本中是否存在隐写字符
        
        Args:
            text: 要检测的文本
            
        Returns:
            如果检测到隐写字符返回True，否则返回False
        """
        logger.info(f"[ContextStabilizer] 隐写扫描 | 文本长度: {len(text)} 字符 | 检测模式数: {len(self.patterns)}")
        for pattern in self.patterns:
            match = pattern.search(text)
            if match:
                matched_char = match.group()
                char_code = f"U+{ord(matched_char):04X}"
                logger.info(f"[ContextStabilizer] 隐写检测命中 | 匹配模式: {pattern.pattern} | 字符编码: {char_code}")
                return True
        logger.info(f"[ContextStabilizer] 隐写扫描完成 | 未检测到隐写字符")
        return False
    
    def clean(self, text: str) -> str:
        """清除文本中的隐写字符
        
        Args:
            text: 要清理的文本
            
        Returns:
            清理后的文本
        """
        result = text
        for pattern in self.patterns:
            result = pattern.sub('', result)
        return result
    
    def get_detected_chars(self, text: str) -> List[str]:
        """获取检测到的隐写字符
        
        Args:
            text: 要检测的文本
            
        Returns:
            检测到的隐写字符列表
        """
        detected = []
        for pattern in self.patterns:
            matches = pattern.findall(text)
            detected.extend(matches)
        return detected
    
    def get_detection_report(self, text: str) -> dict:
        """获取详细的检测报告
        
        Args:
            text: 要检测的文本
            
        Returns:
            包含检测结果的字典
        """
        detected_chars = self.get_detected_chars(text)
        char_codes = [f"U+{ord(c):04X}" for c in detected_chars]
        
        report = {
            'detected': len(detected_chars) > 0,
            'count': len(detected_chars),
            'chars': detected_chars,
            'char_codes': char_codes
        }
        
        logger.info(f"[ContextStabilizer] 隐写检测报告 | 检测到: {'是' if report['detected'] else '否'} | 数量: {report['count']} | 编码: {char_codes[:10]}{'...' if len(char_codes) > 10 else ''}")
        return report
