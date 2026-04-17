"""频率计数器 - 管理各会话的审查频率计数"""

import logging
import json
from typing import Dict, Any

logger = logging.getLogger(__name__)


class FrequencyCounter:
    """管理各会话的审查频率计数"""
    
    STORAGE_KEY_PREFIX = "ctx_stab_counter_"
    ADAPTIVE_KEY_PREFIX = "ctx_stab_adaptive_"
    
    def __init__(self, plugin, frequency: int):
        """
        初始化频率计数器
        
        Args:
            plugin: 插件实例，用于访问存储API
            frequency: 审查频率，表示每隔多少轮进行一次审查
        """
        self.plugin = plugin
        self.frequency = frequency
    
    async def get_count(self, session_name: str) -> int:
        """获取当前计数
        
        Args:
            session_name: 会话名称
            
        Returns:
            当前计数值
        """
        key = f"{self.STORAGE_KEY_PREFIX}{session_name}"
        try:
            data = await self.plugin.get_plugin_storage(key)
            if data:
                return int(data.decode('utf-8'))
            return 0
        except Exception as e:
            logger.debug(f"获取计数器值失败: {e}")
            return 0
    
    async def increment(self, session_name: str):
        """增加计数
        
        Args:
            session_name: 会话名称
        """
        current = await self.get_count(session_name)
        key = f"{self.STORAGE_KEY_PREFIX}{session_name}"
        new_value = current + 1
        await self.plugin.set_plugin_storage(key, str(new_value).encode('utf-8'))
        logger.debug(f"会话 {session_name} 计数器增加到 {new_value}")
    
    async def reset(self, session_name: str):
        """重置计数
        
        Args:
            session_name: 会话名称
        """
        key = f"{self.STORAGE_KEY_PREFIX}{session_name}"
        await self.plugin.set_plugin_storage(key, b'0')
        logger.debug(f"会话 {session_name} 计数器已重置")
    
    async def should_audit(self, session_name: str) -> bool:
        """判断是否应该进行审查
        
        Args:
            session_name: 会话名称
            
        Returns:
            是否应该进行审查
        """
        current = await self.get_count(session_name)
        should = current >= self.frequency - 1
        logger.debug(f"会话 {session_name} 计数: {current}/{self.frequency}, 是否审查: {should}")
        return should
    
    # ========== 动态频率相关方法 ==========
    
    async def _get_adaptive_data(self, session_name: str) -> Dict[str, Any]:
        """获取会话的动态频率数据
        
        Args:
            session_name: 会话名称
            
        Returns:
            动态频率数据字典，包含 consecutive_passes 和 current_frequency
        """
        key = f"{self.ADAPTIVE_KEY_PREFIX}{session_name}"
        try:
            data = await self.plugin.get_plugin_storage(key)
            if data:
                return json.loads(data.decode('utf-8'))
            return {"consecutive_passes": 0, "current_frequency": None}
        except Exception as e:
            logger.debug(f"获取动态频率数据失败: {e}")
            return {"consecutive_passes": 0, "current_frequency": None}
    
    async def _set_adaptive_data(self, session_name: str, data: Dict[str, Any]):
        """保存会话的动态频率数据
        
        Args:
            session_name: 会话名称
            data: 动态频率数据字典
        """
        key = f"{self.ADAPTIVE_KEY_PREFIX}{session_name}"
        await self.plugin.set_plugin_storage(key, json.dumps(data).encode('utf-8'))
    
    async def get_current_frequency(self, session_name: str, base_frequency: int) -> int:
        """获取当前审查频率
        
        Args:
            session_name: 会话名称
            base_frequency: 基础审查频率
            
        Returns:
            当前审查频率
        """
        adaptive_data = await self._get_adaptive_data(session_name)
        current_freq = adaptive_data.get("current_frequency")
        if current_freq is None:
            return base_frequency
        return current_freq
    
    async def record_audit_result(
        self,
        session_name: str,
        passed: bool,
        base_frequency: int,
        frequency_increase_step: int = 1,
        frequency_recovery_threshold: int = 3,
        min_audit_frequency: int = 1
    ) -> Dict[str, Any]:
        """记录审查结果并调整频率
        
        Args:
            session_name: 会话名称
            passed: 审查是否通过
            base_frequency: 基础审查频率
            frequency_increase_step: 失败时频率增加步长
            frequency_recovery_threshold: 连续通过多少次后恢复一级频率
            min_audit_frequency: 最小审查间隔（最高频率）
            
        Returns:
            包含调整信息的字典：
            - old_frequency: 原频率
            - new_frequency: 新频率
            - consecutive_passes: 连续通过次数
            - adjusted: 是否发生了调整
        """
        adaptive_data = await self._get_adaptive_data(session_name)
        consecutive_passes = adaptive_data.get("consecutive_passes", 0)
        current_frequency = adaptive_data.get("current_frequency")
        
        # 如果未初始化，使用基础频率
        if current_frequency is None:
            current_frequency = base_frequency
        
        old_frequency = current_frequency
        adjusted = False
        
        if passed:
            # 审查通过，增加连续通过计数
            consecutive_passes += 1
            
            # 检查是否达到恢复阈值
            if consecutive_passes >= frequency_recovery_threshold and current_frequency < base_frequency:
                # 恢复一级频率（增加间隔）
                new_frequency = min(current_frequency + frequency_increase_step, base_frequency)
                
                logger.info(
                    f"[ContextStabilizer] 频率恢复 | 会话: {session_name} | "
                    f"连续通过: {consecutive_passes} | 频率: {current_frequency} -> {new_frequency}"
                )
                
                current_frequency = new_frequency
                consecutive_passes = 0  # 重置连续通过计数
                adjusted = True
        else:
            # 审查失败，增加频率（减少间隔）
            consecutive_passes = 0  # 重置连续通过计数
            
            if current_frequency > min_audit_frequency:
                new_frequency = max(current_frequency - frequency_increase_step, min_audit_frequency)
                
                logger.info(
                    f"[ContextStabilizer] 动态频率调整 | 会话: {session_name} | "
                    f"原频率: {current_frequency} -> 新频率: {new_frequency}"
                )
                
                current_frequency = new_frequency
                adjusted = True
        
        # 保存更新后的数据
        adaptive_data = {
            "consecutive_passes": consecutive_passes,
            "current_frequency": current_frequency
        }
        await self._set_adaptive_data(session_name, adaptive_data)
        
        return {
            "old_frequency": old_frequency,
            "new_frequency": current_frequency,
            "consecutive_passes": consecutive_passes,
            "adjusted": adjusted
        }
    
    async def should_audit_adaptive(self, session_name: str, base_frequency: int) -> bool:
        """判断是否应该进行审查（考虑动态频率）
        
        Args:
            session_name: 会话名称
            base_frequency: 基础审查频率
            
        Returns:
            是否应该进行审查
        """
        current = await self.get_count(session_name)
        current_frequency = await self.get_current_frequency(session_name, base_frequency)
        should = current >= current_frequency - 1
        logger.debug(
            f"会话 {session_name} 计数: {current}/{current_frequency} (动态), 是否审查: {should}"
        )
        return should
