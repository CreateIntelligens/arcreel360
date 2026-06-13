## ADDED Requirements

### Requirement: GeminiFullRuntimeProvider 必须实现 AssistantRuntimeProvider 协议且 capabilities tier 为 full

系统 SHALL 提供 `GeminiFullRuntimeProvider`，注册到 `runtime_provider_registry`，provider id 为 `gemini-full`。其 `capabilities.tier` MUST 为 `full`，且 `supports_tool_calls`、`supports_subagents`、`supports_resume`、`supports_permission_hooks`、`supports_streaming`、`supports_images`、`supports_interrupt` MUST 全部为 `true`。

#### Scenario: 启动时注册成功
- **WHEN** `AssistantService.__init__` 完成
- **THEN** `runtime_provider_registry["gemini-full"]` 存在且其 `capabilities.tier == "full"`

#### Scenario: SSE event 携带 capabilities
- **WHEN** 客户端订阅 `gemini-full:` session 的 SSE stream，收到任意 event
- **THEN** event payload 的 `capabilities` 字段 MUST 包含 `{"supports_tool_calls": true, "supports_subagents": true, "supports_resume": true, ...}`，前端 `resolveAssistantCapabilities` 据此关闭「不支援工具」相关 banner

### Requirement: session id 必须以 gemini-full: 前缀标识，可被 infer_provider_id 识别

新建会话时系统 SHALL 生成 `gemini-full:<uuid_hex>` 形式的 session id。`infer_provider_id` 函数 MUST 把该前缀映射到 `gemini-full` provider id。已有的 `gemini:` 前缀（lite session）MUST 继续映射到 `gemini-lite`，不与新前缀冲突。

#### Scenario: 新会话 id 形式正确
- **WHEN** `GeminiFullRuntimeProvider.send_new_session` 创建会话
- **THEN** 返回的 session_id MUST 匹配正则 `^gemini-full:[0-9a-f]{32}$`

#### Scenario: 旧 lite session 不被误路由
- **WHEN** 已存在 `gemini:abc123...` 的 lite session
- **THEN** `infer_provider_id("gemini:abc123...") == "gemini-lite"`，不会被新 provider 处理

### Requirement: 工具循环必须以 Gemini 原生 function calling 实现，并支持流式输出

系统 SHALL 用 `google-genai` SDK 的 `Tool(function_declarations=[...])` 配合 `generate_content_stream` 实现工具循环：模型每轮可吐零個、一個或多個 `functionCall`，系统执行对应工具后构造 `functionResponse` 喂回模型，循环直至模型给出无 functionCall 的纯文本响应或主动 stop。

#### Scenario: 单轮工具调用
- **WHEN** 用户消息触发模型返回单個 `functionCall(name="generate_script", args=...)`
- **THEN** 系统执行 generate_script，把结果以 `functionResponse(name="generate_script", response=<result>)` 喂回模型，模型继续生成最终回复

#### Scenario: 多轮工具调用
- **WHEN** 模型在第 N 轮回复中再次返回 `functionCall`
- **THEN** 系统继续执行新工具并喂回，循环 MUST 在不超过配置的最大轮数（默认 20）内自然终止或主动报错终止

#### Scenario: 流式 token 输出
- **WHEN** 模型返回纯文本响应过程中
- **THEN** 系统 MUST 以 `stream_event` 增量推送 token 给前端，最终汇总为 `assistant` message 写入 `agent_messages` 表

#### Scenario: 超过最大循环轮数
- **WHEN** 工具循环达到最大轮数仍未终止
- **THEN** 系统 MUST 写入 `result(subtype="max_turns", is_error=true)` 并终止 session 进入 `error` 状态

### Requirement: session 持久化必须复用 agent_messages 表，新增 tool_use / tool_result type

系统 SHALL 把工具调用相关消息以 `tool_use` 与 `tool_result` 两种新 type 持久化到 `agent_messages.payload`，与既有 `user` / `assistant` / `result` 共存。turn_grouper 与 stream_projector MUST 能识别并按 turn 分组。

#### Scenario: tool_use 消息持久化
- **WHEN** 模型返回 `functionCall` 被系统接住
- **THEN** 一条 `{"type": "tool_use", "name": "<tool>", "input": {...}, "tool_use_id": "<uuid>", "uuid": "<msg_uuid>", "timestamp": "..."}` MUST 被 append 进 `agent_messages`

#### Scenario: tool_result 消息持久化
- **WHEN** 系统执行完工具
- **THEN** 一条 `{"type": "tool_result", "tool_use_id": "<同上>", "content": <result_or_error>, "is_error": false, "uuid": "...", "timestamp": "..."}` MUST 被 append

#### Scenario: 程序重启后历史可恢复
- **WHEN** arcreel 容器重启后用户重新打开同一 session
- **THEN** `read_history_messages` MUST 从 DB 返回完整序列（含 user / tool_use / tool_result / assistant），前端能重建工具调用 turn

### Requirement: 中断与超时必须能终止工具循环且不破坏 DB 一致性

用户调用 `interrupt_session` 时，系统 SHALL 在当前正在执行的工具完成后停止下一轮 `generate_content_stream` 启动，把 session 状态置为 `interrupted`。心跳超时（`ASSISTANT_STREAM_HEARTBEAT_SECONDS`）触发时同样行为。

#### Scenario: 用户中断
- **WHEN** 工具 A 执行中，用户点击中断
- **THEN** 工具 A 完成执行，下一轮模型调用不再启动；session 状态变为 `interrupted`；已落库的 tool_use / tool_result 不被回滚

#### Scenario: 心跳超时
- **WHEN** `generate_content_stream` 超过心跳秒数无新 token
- **THEN** 系统 MUST 取消该流，写入 `result(subtype="timeout", is_error=true)`，session 状态置为 `error`

### Requirement: 与 gemini-lite 的能力边界必须明确

`gemini-full` provider MUST NOT 处理 `gemini:` 前缀的 session（属于 lite）；反之 `gemini-lite` MUST NOT 处理 `gemini-full:` 前缀。两条 provider 共享同一组底层模型与 API key，但 capabilities 与工具循环行为独立。

#### Scenario: 用户在 settings 切换模式不影响旧 session
- **WHEN** 用户原有一個 `gemini:` lite session，把默认 provider 切到 `gemini-full`
- **THEN** 旧 lite session MUST 仍可继续在 lite provider 上读历史；新对话才走 full provider 创建 `gemini-full:` session
