# Context Stabilizer Plugin

A LangBot plugin that validates and manages conversation context using an audit model.

## Features

- **Context Auditing**: Uses a secondary LLM model (Model B) to audit conversation context
- **Steganography Detection**: Detects hidden characters and zero-width characters that may indicate injection attacks
- **Context Compression**: Automatically compresses long context while preserving key information
- **Prompt Injection Protection**: Injects original system prompt reminder after compression
- **Adaptive Audit Frequency**: Automatically adjusts audit frequency based on audit results
- **Configurable Frequency**: Set how often to audit (every N conversation rounds)
- **Timeout Protection**: Prevents auditing from blocking the main conversation flow

## Installation

1. Download the plugin
2. Place it in the LangBot plugins directory
3. Configure the plugin in the LangBot web interface

## Configuration

### Audit Model Settings

| Config | Description | Default |
|--------|-------------|---------|
| audit_model_uuid | The LLM model used for auditing | Required |
| audit_system_prompt | System prompt for the audit model | Built-in |

### Frequency Settings

| Config | Description | Default |
|--------|-------------|---------|
| audit_frequency | Rounds between audits | 3 |
| enable_adaptive_frequency | Auto-adjust frequency based on results | false |
| frequency_increase_step | Frequency increase step on failure | 1 |
| frequency_recovery_threshold | Passes needed before decreasing frequency | 3 |
| min_audit_frequency | Minimum interval (highest frequency) | 1 |

### Timeout Settings

| Config | Description | Default |
|--------|-------------|---------|
| audit_timeout_seconds | Audit timeout in seconds | 10 |
| timeout_action | Action on timeout (remove_chunk/compress_all) | remove_chunk |

### Compression Settings

| Config | Description | Default |
|--------|-------------|---------|
| max_context_length | Max messages before compression | 50 |
| compress_target_length | Target messages after compression | 10 |
| compression_model_uuid | Model for compression (empty = use audit model) | - |
| compression_prompt | Prompt for context summarization | Built-in |
| enable_prompt_injection | Inject original prompt after compression | true |

### Steganography Detection

| Config | Description | Default |
|--------|-------------|---------|
| enable_steganography_detection | Enable hidden character detection | true |
| steganography_patterns | Regex patterns for detection | Built-in |

### Advanced Settings

| Config | Description | Default |
|--------|-------------|---------|
| chunk_size | Messages per audit chunk | 5 |
| enable_logging | Enable detailed logging | false |

## Commands

| Command | Description |
|---------|-------------|
| `!ctxstab status` | View current session audit status |
| `!ctxstab audit` | Force audit on next message |
| `!ctxstab compress` | Force compression on next message |
| `!ctxstab reset` | Reset audit counter |
| `!ctxstab config` | View current configuration |

## How It Works

1. **Event Listening**: Listens to `PromptPreProcessing` event to get conversation context
2. **Frequency Check**: Decides whether to audit based on configured frequency
3. **Steganography Detection**: Detects zero-width and hidden characters in context
4. **Context Splitting**: Splits context into chunks for auditing
5. **Model Auditing**: Uses audit model to check if chunks comply with original settings
6. **Result Processing**: Compresses or removes problematic context based on audit results
7. **Adaptive Frequency**: Adjusts audit frequency based on pass/fail results (if enabled)

## License

MIT
# LangContextStabilizer
