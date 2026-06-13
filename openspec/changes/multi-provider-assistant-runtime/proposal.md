## Why

当前 ArcReel 的对话式助手完全绑定 Claude Agent SDK，导致 Anthropic 配置缺失时，助手能力不可用，且前端将该状态表达为接近"系统未完成配置"。这对只使用 Gemini 或 OpenAI/ChatGPT 的二开場景都不成立，也阻碍了将助手能力演进为可替换的产品层能力。

如果继续维持当前结构，任何 Gemini 或 OpenAI assistant 尝试都会被迫模拟 Claude SDK 的会话、tool use、resume、subagent 与 transcript 语义，技术风险高、演进成本大。因此需要先将 assistant runtime 从"Claude 专用实现"重构为"多 provider、按能力分层"的架构，并在同一套 proposal 中纳入 Gemini 与 OpenAI/ChatGPT 两类 provider。

## What Changes

- 新增 `assistant-runtime-portability` capability，定义 provider 抽象、能力矩阵、可用性协商与分层能力模型
- 引入 `Gemini assistant` 与 `OpenAI/ChatGPT assistant` 两类 provider，首期都以 lite / chat-copilot 形态落地：支持项目内对话、文本/图片输入、有限工具调用、统一流式输出
- 明确区分本项目真正需要的 `workflow-grade` 能力与 Claude SDK 专属 full runtime 能力，避免把"需要工作流编排"误解成"必须复制 Claude SDK 全部协议"
- 调整同步助手端点语义，使其通过"当前激活 assistant provider"路由，而不是默认等同 Claude runtime
- 调整系统配置页与全局配置完整性语义：Anthropic 不再被视为全局必填项，而是当前 assistant provider 为 Claude 时的 provider-specific requirement；Gemini 与 OpenAI 也各自暴露 provider-specific requirement
- 保留 Claude runtime 作为 full capability provider；Gemini 与 OpenAI/ChatGPT 首期作为 lite capability provider，并为后续 workflow-grade 扩展预留接口

## Capabilities

### New Capabilities

- `assistant-runtime-portability`：多 provider assistant runtime 抽象、能力协商、能力分层与 provider 状态暴露

### Modified Capabilities

- `sync-agent-chat`：同步对话端点改为走当前激活 provider，并在能力不足时返回结构化降级信息
- `system-config-ui`：配置页与全局警告从"Anthropic 必填"改为"当前 assistant provider 所需凭证"，避免误伤 Gemini-only 或 OpenAI-only 場景

## Impact

- **后端核心改动**：`server/agent_runtime/session_manager.py`、`server/agent_runtime/service.py`、`server/routers/assistant.py`、`server/routers/agent_chat.py`
- **配置与状态改动**：`server/routers/system_config.py`、`lib/config/service.py`、`frontend/src/stores/config-status-store.ts`
- **前端交互改动**：`frontend/src/components/pages/AgentConfigTab.tsx`、`frontend/src/components/pages/SystemConfigPage.tsx`、助手面板相关状态与类型定义
- **复用资产**：`lib/text_backends/gemini.py`、現有 Gemini provider 配置体系、現有 OpenAI 兼容 provider / backend 封装、現有项目上下文构建与消息流 UI
- **首期目标**：Gemini 与 OpenAI/ChatGPT 的 lite assistant；Claude 保留 full runtime
- **后续阶段目标**：按本项目的小说转短视频工作流需要，逐步补齐 workflow-grade 能力，而不是复制 Claude SDK 全部协议

## Migration Notes

- `assistant_provider=claude` 仍是默认行为，現有 Anthropic 用户不需要修改配置
- `assistant_provider=gemini-lite` 或 `assistant_provider=openai-lite` 后，系统配置完整性检查将改为对应 provider-specific requirement，不再把 Anthropic 视为全局必填
- Gemini-lite 与 OpenAI-lite 首期定位是项目内 copilot，不承诺 Claude full runtime 的 resume、subagent、permission hook 等能力
- 若前端检测到 capability 不支持，应显示结构化降级提示，而不是继续暴露 Claude-only 入口