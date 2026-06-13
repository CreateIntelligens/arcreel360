## ADDED Requirements

### Requirement: OpenAIFullRuntimeProvider 必須實作 AssistantRuntimeProvider 協議且 capabilities tier 為 full

系統 SHALL 提供 `OpenAIFullRuntimeProvider`,註冊到 `runtime_provider_registry`,provider id 為 `openai-full`。其 `capabilities.tier` MUST 為 `full`,且 `supports_tool_calls`、`supports_subagents`、`supports_resume`、`supports_permission_hooks`、`supports_streaming`、`supports_images`、`supports_interrupt` MUST 全部為 `true`。

#### Scenario: 啟動時註冊成功
- **WHEN** `AssistantService.__init__` 完成
- **THEN** `runtime_provider_registry["openai-full"]` 存在且其 `capabilities.tier == "full"`

#### Scenario: SSE event 攜帶 capabilities
- **WHEN** 客戶端訂閱 `openai-full:` session 的 SSE stream,收到任意 event
- **THEN** event payload 的 `capabilities` 欄位 MUST 包含 `{"supports_tool_calls": true, "supports_subagents": true, "supports_resume": true, ...}`,前端 `resolveAssistantCapabilities` 據此關閉「不支援工具」相關 banner

### Requirement: session id 必須以 openai-full: 前綴標識,可被 infer_provider_id 識別

新建會話時系統 SHALL 產生 `openai-full:<uuid_hex>` 形式的 session id。`infer_provider_id` 函式 MUST 把該前綴映射到 `openai-full` provider id。既有的 `openai:` 前綴(lite session)MUST 繼續映射到 `openai-lite`,不與新前綴衝突。

#### Scenario: 新會話 id 形式正確
- **WHEN** `OpenAIFullRuntimeProvider.send_new_session` 建立會話
- **THEN** 回傳的 session_id MUST 匹配正則 `^openai-full:[0-9a-f]{32}$`

#### Scenario: 舊 lite session 不被誤路由
- **WHEN** 已存在 `openai:abc123...` 的 lite session
- **THEN** `infer_provider_id("openai:abc123...") == "openai-lite"`,不會被新 provider 處理

### Requirement: 工具循環必須以 OpenAI Agents SDK 實作,並支援流式輸出

系統 SHALL 用 `openai_agents.Agent` + `Runner.run_streamed(agent, input=[...])` 實作工具循環:模型每輪可吐零個、一個或多個 tool call,SDK 自動執行 `FunctionTool.on_invoke_tool` 並餵回結果,迴圈直至模型給出無 tool call 的純文字回應或主動 stop。

`Agent` 必須以下列方式組裝:
- `tools` 引數注入 11 個 `FunctionTool` instance(7 個 skill + `fs_read`、`fs_write`、`fs_list`、`run_subagent`),其中 `params_json_schema` 直接複用 `SKILL_DECLARATIONS` 中的手調 schema(經 `_gemini_to_openai_schema()` 轉換成 OpenAI JSON Schema dialect)。
- 每個 tool 的 `on_invoke_tool` MUST 透過 `permission_gate.as_openai_wrapper()` 包裝,deny 時回傳 `{"permission_denied": True, ...}` dict,SDK Runner 把 dict 當 tool output 餵回模型(對話不中斷)。
- `session=None`:**禁用** SDK 內建 session memory;每次 `Runner.run_streamed()` 從 `agent_messages` 表讀完整歷史餵 `input=[...]`。

工具循環在不超過配置的最大輪數(預設 20)內自然終止或主動報錯終止。

#### Scenario: 單輪工具呼叫
- **WHEN** 使用者訊息觸發模型回傳單個 tool call(name=generate_script)
- **THEN** SDK Runner 自動執行對應 `FunctionTool.on_invoke_tool`(內部呼叫既有 `SKILL_HANDLERS["generate_script"]`),產生 `ToolCallOutputItem` 餵回模型,模型繼續產生最終回覆

#### Scenario: 多輪工具呼叫
- **WHEN** 模型在第 N 輪回覆中再次回傳 tool call
- **THEN** SDK Runner 繼續執行新工具並餵回,迴圈 MUST 在不超過設定的最大輪數內自然終止或主動報錯終止

#### Scenario: 流式 token 輸出
- **WHEN** 模型回傳純文字回應過程中
- **THEN** 系統 MUST 從 SDK Runner 的 `RunItem` / `RawResponseStreamEvent`(包含 text deltas)以 `stream_event` 增量推送 token 給前端,最終彙總為 `assistant` message 寫入 `agent_messages` 表

#### Scenario: 超過最大迴圈輪數
- **WHEN** 工具迴圈達到最大輪數仍未終止
- **THEN** 系統 MUST 寫入 `result(subtype="max_turns", is_error=true)` 並終止 session 進入 `error` 狀態

### Requirement: session 持久化必須複用 agent_messages 表,不引入 SDK 內建 session memory

系統 SHALL 把所有訊息(user / tool_use / tool_result / assistant / thinking)寫入既有 `agent_messages` 表,複用 `gemini-full` 與 `claude` provider 的 schema 與類型。`Runner.run_streamed()` 的 `session` 引數 MUST 為 `None`;歷史一律從 `agent_messages` 讀出後轉為 SDK input list 餵入。

#### Scenario: tool_use 訊息持久化
- **WHEN** 模型回傳 tool call,SDK Runner 觸發 `on_invoke_tool`
- **THEN** 一筆 `{"type": "tool_use", "name": "<tool>", "input": {...}, "tool_use_id": "<uuid>", "uuid": "<msg_uuid>", "timestamp": "..."}` MUST 被 append 進 `agent_messages`

#### Scenario: tool_result 訊息持久化
- **WHEN** SDK Runner 執行完工具產生 `ToolCallOutputItem`
- **THEN** 一筆 `{"type": "tool_result", "tool_use_id": "<同上>", "content": <result_or_error>, "is_error": false, "uuid": "...", "timestamp": "..."}` MUST 被 append

#### Scenario: permission deny 訊息持久化
- **WHEN** `on_invoke_tool` 包裝層偵測到 gate deny,回傳 `{"permission_denied": True, ...}` dict
- **THEN** 系統 MUST 把該 dict 持久化為 `tool_result` type(`is_error: false` 但 payload 含 `permission_denied: true` metadata),供後續歷史重放與 audit

#### Scenario: 程式重啟後歷史可恢復
- **WHEN** arcreel 容器重啟後使用者重新打開同一 session
- **THEN** `read_history_messages` MUST 從 DB 回傳完整序列(含 user / tool_use / tool_result / assistant);下次 `Runner.run_streamed()` 把該序列轉成 SDK input list 餵入,讓 GPT 模型繼續對話

#### Scenario: SDK 內建 session 不被啟用
- **GIVEN** 任何 `Runner.run_streamed()` 呼叫
- **THEN** `session` 引數 MUST 為 `None`;測試 MUST 驗證若誤傳非 None 值會被攔截或 log warning

### Requirement: 中斷與超時必須能終止工具循環且不破壞 DB 一致性

使用者呼叫 `interrupt_session` 時,系統 SHALL 在當前正在執行的工具完成後停止下一輪 SDK Runner 啟動,把 session 狀態置為 `interrupted`。心跳超時(`ASSISTANT_STREAM_HEARTBEAT_SECONDS`)觸發時同樣行為。

#### Scenario: 使用者中斷
- **WHEN** 工具 A 執行中,使用者點擊中斷
- **THEN** 工具 A 完成執行,下一輪模型呼叫不再啟動;session 狀態變為 `interrupted`;已落庫的 tool_use / tool_result 不被回滾

#### Scenario: 心跳超時
- **WHEN** SDK Runner 過心跳秒數無新 token
- **THEN** 系統 MUST 取消該 stream,寫入 `result(subtype="timeout", is_error=true)`,session 狀態置為 `error`

### Requirement: 與 openai-lite 的能力邊界必須明確

`openai-full` provider MUST NOT 處理 `openai:` 前綴的 session(屬於 lite);反之 `openai-lite` MUST NOT 處理 `openai-full:` 前綴。兩條 provider 共享同一組底層模型與 API key,但 capabilities 與工具循環行為獨立;`openai-lite` 不引入 `openai-agents` SDK 依賴。

#### Scenario: 使用者在 settings 切換模式不影響舊 session
- **WHEN** 使用者原有一個 `openai:` lite session,把預設 provider 切到 `openai-full`
- **THEN** 舊 lite session MUST 仍可繼續在 lite provider 上讀歷史;新對話才走 full provider 建立 `openai-full:` session
