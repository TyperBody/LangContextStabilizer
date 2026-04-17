"""上下文稳定器命令组件 - 提供用户命令接口"""
from __future__ import annotations

import logging
from typing import AsyncGenerator

from langbot_plugin.api.definition.components.command.command import Command
from langbot_plugin.api.entities.builtin.command.context import ExecuteContext, CommandReturn

logger = logging.getLogger(__name__)


class CtxstabCommand(Command):
    """上下文稳定器命令组件"""
    
    def __init__(self):
        """初始化命令组件"""
        super().__init__()
        
        logger.info("上下文稳定器命令组件初始化")
        
        @self.subcommand(
            name="",
            help="显示上下文稳定器帮助信息",
            usage="ctxstab",
            aliases=["cs"]
        )
        async def root(self, context: ExecuteContext) -> AsyncGenerator[CommandReturn, None]:
            help_text = """📊 上下文稳定器命令帮助

!ctxstab status  - 查看当前会话的审查状态
!ctxstab audit   - 手动触发一次上下文审查
!ctxstab compress - 手动强制压缩当前上下文
!ctxstab reset   - 重置审查计数器
!ctxstab config  - 查看当前配置

别名: !cs"""
            yield CommandReturn(text=help_text)
        
        @self.subcommand(
            name="status",
            help="查看当前会话的审查状态和统计",
            usage="ctxstab status",
            aliases=["s"]
        )
        async def status(self, context: ExecuteContext) -> AsyncGenerator[CommandReturn, None]:
            session_name = f"{context.session.launcher_type.value}_{context.session.launcher_id}"
            
            # 获取计数器值
            key = f"ctx_stab_counter_{session_name}"
            try:
                data = await self.plugin.get_plugin_storage(key)
                if data:
                    count = int(data.decode('utf-8'))
                else:
                    count = 0
            except Exception:
                count = 0
            
            config = self.plugin.get_config()
            frequency = config.get('audit_frequency', 3)
            next_audit = frequency - count
            if next_audit <= 0:
                next_audit_text = "下一轮"
            else:
                next_audit_text = f"{next_audit} 轮后"
            
            status_text = f"""📊 上下文稳定器状态

📍 会话: {session_name}
🔢 当前计数: {count}/{frequency}
⏰ 下次审查: {next_audit_text}
🤖 审查模型: {config.get('audit_model_uuid', '未配置') or '未配置'}
🔍 隐写检测: {'✅ 启用' if config.get('enable_steganography_detection', True) else '❌ 禁用'}
📏 最大上下文: {config.get('max_context_length', 20)} 条消息
⏱️ 审查超时: {config.get('audit_timeout_seconds', 10)} 秒"""
            
            yield CommandReturn(text=status_text)
        
        @self.subcommand(
            name="reset",
            help="重置审查计数器",
            usage="ctxstab reset",
            aliases=["r"]
        )
        async def reset(self, context: ExecuteContext) -> AsyncGenerator[CommandReturn, None]:
            session_name = f"{context.session.launcher_type.value}_{context.session.launcher_id}"
            key = f"ctx_stab_counter_{session_name}"
            await self.plugin.set_plugin_storage(key, b'0')
            
            logger.info(f"[{session_name}] 审查计数器已重置")
            yield CommandReturn(text=f"✅ 已重置会话 {session_name} 的审查计数器")
        
        @self.subcommand(
            name="config",
            help="查看当前配置",
            usage="ctxstab config",
            aliases=["c"]
        )
        async def show_config(self, context: ExecuteContext) -> AsyncGenerator[CommandReturn, None]:
            config = self.plugin.get_config()
            
            config_text = f"""⚙️ 上下文稳定器配置

🔄 审查频率: 每 {config.get('audit_frequency', 3)} 轮
⏱️ 审查超时: {config.get('audit_timeout_seconds', 10)} 秒
🚨 超时策略: {config.get('timeout_action', 'remove_chunk')}
📏 最大上下文: {config.get('max_context_length', 20)} 条
📦 压缩目标: {config.get('compress_target_length', 5)} 条
📐 分块大小: {config.get('chunk_size', 5)} 条
🔍 隐写检测: {'启用' if config.get('enable_steganography_detection', True) else '禁用'}
📝 详细日志: {'启用' if config.get('enable_logging', False) else '禁用'}"""
            
            yield CommandReturn(text=config_text)
        
        @self.subcommand(
            name="audit",
            help="手动触发上下文审查（下次对话生效）",
            usage="ctxstab audit",
            aliases=["a"]
        )
        async def force_audit(self, context: ExecuteContext) -> AsyncGenerator[CommandReturn, None]:
            session_name = f"{context.session.launcher_type.value}_{context.session.launcher_id}"
            
            # 设置计数器到触发值
            config = self.plugin.get_config()
            frequency = config.get('audit_frequency', 3)
            
            key = f"ctx_stab_counter_{session_name}"
            await self.plugin.set_plugin_storage(key, str(frequency - 1).encode('utf-8'))
            
            logger.info(f"[{session_name}] 已设置下次对话强制审查")
            yield CommandReturn(text="✅ 已设置强制审查，下次对话将触发上下文审查")
        
        @self.subcommand(
            name="compress",
            help="标记下次对话强制压缩上下文",
            usage="ctxstab compress"
        )
        async def force_compress(self, context: ExecuteContext) -> AsyncGenerator[CommandReturn, None]:
            session_name = f"{context.session.launcher_type.value}_{context.session.launcher_id}"
            
            # 设置强制压缩标记
            key = f"ctx_stab_force_compress_{session_name}"
            await self.plugin.set_plugin_storage(key, b'1')
            
            logger.info(f"[{session_name}] 已设置下次对话强制压缩")
            yield CommandReturn(text="✅ 已设置强制压缩，下次对话将压缩上下文")
