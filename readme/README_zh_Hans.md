# 上下文稳定器插件

一个使用审查模型验证和管理对话上下文的 LangBot 插件。

## 功能特性

- **上下文审查**: 使用辅助 LLM 模型（模型B）审查对话上下文
- **隐写检测**: 检测可能表示注入攻击的隐藏字符和零宽字符
- **上下文压缩**: 自动压缩过长的上下文，同时保留关键信息
- **Prompt注入保护**: 在压缩后注入原始系统提示词提醒
- **动态审查频率**: 根据审查结果自动调整审查频率
- **可配置频率**: 设置审查频率（每N轮对话审查一次）
- **超时保护**: 防止审查阻塞主对话流程

## 安装

1. 下载插件
2. 将其放置在 LangBot 插件目录中
3. 在 LangBot Web 界面中配置插件

## 配置项

### 审查模型设置

| 配置 | 描述 | 默认值 |
|------|------|--------|
| audit_model_uuid | 用于审查的 LLM 模型 | 必填 |
| audit_system_prompt | 审查模型的系统提示词 | 内置 |

### 频率设置

| 配置 | 描述 | 默认值 |
|------|------|--------|
| audit_frequency | 审查间隔轮数 | 3 |
| enable_adaptive_frequency | 根据审查结果自动调整频率 | false |
| frequency_increase_step | 审查失败时频率增加步长 | 1 |
| frequency_recovery_threshold | 连续通过多少次后降低频率 | 3 |
| min_audit_frequency | 最小审查间隔（最高频率） | 1 |

### 超时设置

| 配置 | 描述 | 默认值 |
|------|------|--------|
| audit_timeout_seconds | 审查超时时间（秒） | 10 |
| timeout_action | 超时处理策略 | remove_chunk |

### 压缩设置

| 配置 | 描述 | 默认值 |
|------|------|--------|
| max_context_length | 触发压缩的最大消息数 | 50 |
| compress_target_length | 压缩后目标消息数 | 10 |
| compression_model_uuid | 压缩模型（留空使用审查模型） | - |
| compression_prompt | 上下文摘要的提示词 | 内置 |
| enable_prompt_injection | 压缩后注入原始Prompt提醒 | true |

### 隐写检测

| 配置 | 描述 | 默认值 |
|------|------|--------|
| enable_steganography_detection | 启用隐写检测 | true |
| steganography_patterns | 检测正则表达式模式 | 内置 |

### 高级设置

| 配置 | 描述 | 默认值 |
|------|------|--------|
| chunk_size | 每个审查块的消息数 | 5 |
| enable_logging | 启用详细日志 | false |

## 命令

| 命令 | 描述 |
|------|------|
| `!ctxstab status` | 查看当前会话审查状态 |
| `!ctxstab audit` | 强制下次消息进行审查 |
| `!ctxstab compress` | 强制下次消息压缩上下文 |
| `!ctxstab reset` | 重置审查计数器 |
| `!ctxstab config` | 查看当前配置 |

## 工作原理

1. **事件监听**: 监听 `PromptPreProcessing` 事件获取对话上下文
2. **频率检查**: 根据配置的审查频率决定是否进行审查
3. **隐写检测**: 检测上下文中的零宽字符等隐写字符
4. **上下文拆分**: 将上下文拆分成多个块进行审查
5. **模型审查**: 调用审查模型检查各块是否符合原始设定
6. **结果处理**: 根据审查结果决定是否压缩或移除上下文
7. **动态频率**: 根据通过/失败结果调整审查频率（如启用）

## 许可证

MIT
