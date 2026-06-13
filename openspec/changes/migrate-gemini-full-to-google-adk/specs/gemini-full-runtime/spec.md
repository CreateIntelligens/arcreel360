## MODIFIED Requirements

### Requirement: 工具循環必須以 Gemini 原生 function calling 實現,並支援流式輸出

系統 SHALL 透過 `google-adk` 的 `Agent` + `Runner.run_async()` 執行工具循環,**不再自維護** `functionCall` / `functionResponse` 配對邏輯。`Runner.run_async()` 會以 async iterator 形式產出 `Event`,系統 MUST 把 events 投影到既有 SSE buffer。

`Agent` 必須以下列方式組裝:
- `tools` 引數注入 7 個 skill 的 `BaseTool` 子類 instance(由 `adk_tool_adapters.py` 建立),覆寫 `_get_declaration()` 直接回傳 `SKILL_DECLARATIONS` 中的手調 `FunctionDeclaration`,而非讓 ADK 從 Python signature 自動推導。
- `before_tool_callback` 引數注入 `permission_gate.as_adk_callback(gate)` 回傳的 callable,deny 時回傳 dict 讓 ADK 跳過 tool 執行並把 dict 當 tool result 回模型(對話不中斷)。
- `session_service` 引數注入 `AgentMessagesSessionService(BaseSessionService)` 自訂實作,把所有 session events 落到既有 `agent_messages` 表;ADK 內建的 `InMemorySessionService` / `DatabaseSessionService` 禁止使用。

工具循環在不超過配置的最大輪數(預設 20)內自然終止或主動報錯終止。

#### Scenario: 單輪工具呼叫
- **WHEN** 使用者訊息觸發模型回傳單個 `functionCall(name="generate_script", args=...)`
- **THEN** ADK Runner 自動執行對應 `SkillBaseTool.run_async()`(內部呼叫 `skill_function_declarations` 的 handler),產生 `Event(content=function_response)` 餵回模型,模型繼續產生最終回覆

#### Scenario: 多輪工具呼叫
- **WHEN** 模型在第 N 輪回覆中再次回傳 `functionCall`
- **THEN** ADK Runner 繼續執行新工具並餵回,迴圈 MUST 在不超過設定的最大輪數內自然終止或主動報錯終止

#### Scenario: 流式 token 輸出
- **WHEN** 模型回傳純文字回應過程中
- **THEN** 系統 MUST 從 ADK Event(包含 partial text deltas)以 `stream_event` 增量推送 token 給前端,最終彙總為 `assistant` message 寫入 `agent_messages` 表

#### Scenario: 超過最大迴圈輪數
- **WHEN** 工具迴圈達到最大輪數仍未終止
- **THEN** 系統 MUST 寫入 `result(subtype="max_turns", is_error=true)` 並終止 session 進入 `error` 狀態

#### Scenario: ADK 版本鎖定
- **GIVEN** `pyproject.toml` 中 `google-adk` 版本約束
- **WHEN** 開發者嘗試升級到不相容的 minor 版本
- **THEN** `uv sync` MUST 因版本約束拒絕安裝;升級流程 MUST 走 `docs/adk-upgrade-checklist.md` 記錄的回歸測試

### Requirement: session 持久化必須複用 agent_messages 表,新增 tool_use / tool_result payload type

系統 SHALL 把工具呼叫相關訊息以 `tool_use` 與 `tool_result` 兩種 payload type(寫在 `agent_messages.payload` JSON 內的 `type` 欄位)持久化,與既有 `user` / `assistant` / `result` 共存。`agent_messages` 表 schema **不變**(沒有 `message_type` 欄位,類型由 `payload` JSON 區分)。turn_grouper 與 stream_projector MUST 能識別並按 turn 分組。

**新增約束**:持久化 MUST 透過下列兩種策略之一,具體選擇在 Phase 1 spike day 4 做 go/no-go 決定:

**策略 A(優先)**:`AgentMessagesSessionService(BaseSessionService)` 自訂實作,覆寫 ADK `BaseSessionService` 的 4 個 abstract method:
- `create_session(*, app_name, user_id, state, session_id)`:若 `session_id` 為 None 則以 `build_external_session_id("gemini-full", uuid4().hex)` 產生;呼叫既有 `agent_session_repo.create()` 寫入 `agent_sessions` 表;回傳 `Session(id=session_id, app_name=app_name, user_id=user_id, state=state or {}, events=[])`。`app_name` MUST 為 `"arcreel"`,`user_id` MUST 為對應 project 名(純 audit 用,不影響業務)。
- `get_session(*, app_name, user_id, session_id, config)`:從 `agent_messages` 讀所有 `sdk_session_id=session_id` 的 row(按 `seq` 排序),把每筆 `payload` JSON 反序列化為 `Event`,重建 `Session` 物件回傳。
- `list_sessions(*, app_name, user_id)`:從 `agent_sessions` 表查所有 user 的 session,回傳 `ListSessionsResponse`(僅含 metadata,不載入 events)。
- `delete_session(*, app_name, user_id, session_id)`:呼叫 `agent_session_repo.delete(session_id)`,FK CASCADE 自動清掉 `agent_messages`。
- `append_event(session, event)`:覆寫 base 預設行為,先呼叫 `super().append_event(session, event)` 更新 `session.events` 與 state delta,再額外將 event 序列化為 JSON payload 寫入 `agent_messages`(下一個 `seq`)。

**策略 B(fallback)**:若策略 A 在 Phase 1 day 4 LOC checkpoint 超過 ~400 行或邊界 case 過多,改用 ADK 內建 `InMemorySessionService` + 在 provider 層手動雙寫:provider 在每次 `Runner.run_async()` 產出 event 時透過 `_persist_event(event)` hook 將 event 寫入 `agent_messages`;ADK Runner 內部 session state 仍存記憶體(對話結束即丟)。代價:Runner 內部 state 與 DB 不嚴格同步,對話中途崩潰可能丟最後幾個 events。**任一策略採用後 MUST 在 design.md 與此 spec 補後續 PR 註明**。

**Event 序列化格式**:`payload` 內容為 JSON wrapper:

```json
{
  "kind": "adk_event",
  "adk_version": "<google-adk semver>",
  "type": "tool_use" | "tool_result" | "text" | "thinking" | "...",
  "event": {<event.model_dump_json output 完整內容>}
}
```

`type` 欄位由 event 內容推導(見下表),供既有 `turn_grouper` / `stream_projector` 沿用既有解析邏輯。`event` 欄位保留完整 ADK Event,供未來擴充。讀回時若 `adk_version` 與當前不同,先試 `Event.model_validate_json` 直接讀;失敗時 log warning 並降級(把 event.content.parts 重組成純文字 `assistant` 訊息)。

ADK Event ↔ payload `type` 映射:

| Event 內容判定 | payload `type` |
|---|---|
| `event.content.parts[*].text` 含 author=user 文字 | `user` |
| `event.content.parts[*].text` 含 author=model 文字 | `text`(對應前端 assistant turn) |
| `event.content.parts[*].function_call` | `tool_use` |
| `event.content.parts[*].function_response` | `tool_result` |
| `event.content.parts[*].thought` 或 `thought_signature` | `thinking` |
| `event.actions.escalate` / `event.error_code` | `result`(error subtype) |

#### Scenario: tool_use 訊息持久化
- **WHEN** 模型回傳 `functionCall` 被 ADK Runner 接住,觸發 `before_tool_callback` 後執行 tool
- **THEN** session service MUST 把該 event 寫入 `agent_messages`,`payload` 為 `{"kind": "adk_event", "adk_version": "...", "type": "tool_use", "event": {...完整 ADK Event JSON...}}`,既有 turn_grouper 可從 `payload.type == "tool_use"` 識別

#### Scenario: tool_result 訊息持久化
- **WHEN** ADK Runner 執行完工具產生 function_response event
- **THEN** session service MUST 寫入 `payload.type == "tool_result"` 的 row;`event.content.parts[*].function_response.response` 內容包含 tool 回傳值或 error

#### Scenario: permission deny 訊息持久化
- **WHEN** `before_tool_callback` 回傳 deny dict,ADK Runner 跳過 tool 執行並用該 dict 構造 function_response event
- **THEN** 系統 MUST 把該 event 持久化為 `payload.type == "tool_result"`,`event.content.parts[*].function_response.response` 含 `{"permission_denied": true, "reason": ..., "tool": ...}`,供後續歷史重放與 audit

#### Scenario: 程式重啟後歷史可恢復
- **WHEN** arcreel 容器重啟後使用者重新打開同一 session
- **THEN** `AgentMessagesSessionService.get_session(app_name="arcreel", user_id=<project>, session_id=...)` MUST 從 DB 重建完整 ADK `Session` 物件(含 `events` 列表);Runner 在此基礎上繼續對話;前端能重建工具呼叫 turn

#### Scenario: 跨 ADK 版本相容性
- **WHEN** 升級 google-adk 後嘗試讀取舊版本寫入的 session
- **THEN** session service MUST 先試 `Event.model_validate_json` 直接反序列化;失敗時 MUST log warning 含 `adk_version` 差異,並降級為純文字 events;不可拋例外讓 session 完全無法讀取

#### Scenario: 所有 ADK Event 類型可映射
- **WHEN** ADK Runner 產生任何 Event 類型(text、function_call、function_response、thinking、turn_complete、error 等)
- **THEN** session service MUST 能將其映射到 payload `type` 列舉中的某個值;不能映射時 MUST 在開發環境(`DEBUG=true`)拋例外、在 production 寫入 `type: "unknown"` 並 log warning(避免靜默丟資料)
