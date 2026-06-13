## Context

現有 `OpenAILiteProvider`(`server/agent_runtime/text_backend_runtime_provider.py`)只支援純對話,無工具呼叫。OpenAI 2025 年發布 **OpenAI Agents SDK**(`openai-agents-python`,PyPI 套件名 `openai-agents`),提供:

- `Agent(name, instructions, tools, model, ...)`:agent 抽象。
- `Runner.run_streamed(agent, input=[...])`:工具循環引擎,async iterator of `RunItem` / `RawResponseStreamEvent`。
- `FunctionTool(name, description, params_json_schema, on_invoke_tool)`:**支援手寫 schema**,不強制 signature 推導。
- Input/output guardrails(`reject_content`、`needs_approval`):對輸入/輸出做攔截。
- Session 預設不啟用,`Runner.run(input=[...])` 可直接餵完整歷史。

與本次變更直接相關的對比:

| 能力 | OpenAI Agents SDK | Google ADK(對照) | Claude Agent SDK |
|---|---|---|---|
| 手調 tool schema | ✅ `FunctionTool(params_json_schema=)` | ❌ 強制推導,需自寫 BaseTool 子類 | ✅ |
| Session 繞過 | ✅ `session=None`,直接餵 input list | ❌ 必須實作 `BaseSessionService` | ✅ |
| Permission deny → 不中斷 | ⚠️ 需用 input guardrail `reject_content` 模擬 | ✅ `before_tool_callback` 直接支援 | ✅ |
| Streaming | ✅ `RunItem` / Raw events | ✅ `Event` async iter | ✅ |
| 多模型支援 | ⚠️ best-effort beta(LiteLLM 整合) | ✅ Gemini native + LiteLLM | ❌ Claude only |

約束:
- `agent_messages` 表已是跨 provider 真相源,新 provider 必須複用,不能引入 SDK 內建 session memory。
- 既有 7 個 skill 的 `FunctionDeclaration.parameters`(在 `skill_function_declarations.py:81+`)是經過 prompt-tuning 的,schema 描述措辭不可被覆蓋。
- 與並行的 `migrate-gemini-full-to-google-adk` 變更要保持 design 對稱:三家 full-tier provider 都用各自官方 SDK,但**不**強制統一介面到 SDK 抽象 —— 仍透過 ArcReel 自有的 `AssistantRuntimeProvider` 協議對接。
- OpenAI Agents SDK 版本 < 1.0,API 仍可能調整;需鎖 minor 版本並建立升級檢查清單。

利益相關方:OpenAI 使用者(終於能跑漫畫工作流)、後端工程師(實作)、前端(新增 grid 與 label 條目)、運維(新依賴 + env var)。

## Goals / Non-Goals

**Goals:**

- 把 OpenAI 升到 full tier:讓 GPT 模型能執行 7 個 skill + 4 個 fs 工具,完整跑漫畫工作流。
- 直接複用既有 `SKILL_DECLARATIONS` 手調 schema,**零 prompt-tuning 損失**。
- session 持久化複用既有 `agent_messages` 表,不引入新表。
- Permission gate 在新 provider 上的語意與 `gemini-full`(ADK) canonical deny payload 1:1 對齊:deny → 包成 synthetic tool_result 回模型,**對話流不中斷**。
- 與 `migrate-gemini-full-to-google-adk` 對稱:三家 full-tier provider 各自走各家 SDK,但對外契約統一。
- 80%+ 程式碼覆蓋率:單元測試覆蓋 tool adapter、provider 主體、guardrail 整合、session 投影。

**Non-Goals:**

- **不**透過 OpenAI Agents SDK + LiteLLM 重寫 `gemini-full`(LiteLLM 對 Gemini `function_response` / `thought_signature` 等特有語意的支援未在 OpenAI 官方文件中記載,風險高且 1200–1800 LOC 移植成本)。Gemini 端走獨立的 `migrate-gemini-full-to-google-adk` 變更。
- **不**引入單一框架統一三家 provider(沿用 `add-gemini-full-runtime` 的 design.md line 65 判斷:框架反而會變成只服務某一家的偽抽象)。
- **不**動 `openai-lite` provider:純對話路徑保留,使用者可自選 lite vs full。
- **不**引入 OpenAI Agents SDK 的 handoff(agent-to-agent dispatch)、guardrails 之外的進階特性 —— 本次只用 SDK 的工具循環核心。
- **不**支援 OpenAI Agents SDK 的內建 session memory:`Runner.run_streamed(...)` 始終 `session=None`,歷史一律由 `agent_messages` 表餵入。

## Decisions

### 1. session_id 前綴使用 `openai-full:`,與 `openai:` 前綴(lite session)區隔

**選擇**:沿用既有 `build_external_session_id(provider_id, uuid_hex)` 模式,新增 `OPENAI_FULL_PROVIDER_ID = "openai-full"` 常數。`infer_provider_id` 支援:

| 前綴 | 路由到 |
|---|---|
| `claude:` | `claude` |
| `gemini:` | `gemini-lite` |
| `gemini-full:` | `gemini-full` |
| `openai:` | `openai-lite` |
| `openai-full:`(新增) | `openai-full` |

**替代方案**:讓 `openai-full` 與 `openai-lite` 共用 `openai:` 前綴,憑 capability matrix 區分。**否決**:現有 session id 即 routing key,共用會破壞「session id 前綴決定路由」的不變式;切換 provider 後舊 session 會被誤路由。

**理由**:對稱於既有 `gemini` / `gemini-full` 雙前綴設計,維護成本低、行為可預測。

### 2. 不實作 `BaseSessionService`,改用 `Runner.run_streamed(input=[...])` 餵歷史

**選擇**:每次 `send_user_message` 與 `send_new_session` 都從 `agent_messages` 表讀取完整歷史,轉成 OpenAI Agents SDK 的 input list 格式(role + content),`Runner.run_streamed(agent, input=history)` 啟動工具循環。SDK 的 stream events 投影回 `agent_messages` 寫入。

**替代方案**:

- 實作 SDK 的 `Session` 子類橋接 `agent_messages` 表(類比 Google ADK 的 `BaseSessionService`)。**否決**:OpenAI Agents SDK 的 session API 是 opt-in,且最佳實踐是直接 `input=[]` 餵歷史;沒必要為了「對稱」而寫 100+ 行 adapter。
- 用 SDK 內建 session memory。**否決**:會建立雙真相源(SDK in-memory state vs `agent_messages` 表),行為不可預測。

**理由**:OpenAI 這邊 `Runner.run_streamed(input=[...])` 是 SDK 推薦模式,且最少程式碼;每次餵完整歷史的成本,比 Google ADK 自訂 session service 簡單得多。

### 3. Tool adapter 用 `FunctionTool(params_json_schema=...)` 直接吃 `SKILL_DECLARATIONS`

**選擇**:在 `openai_tool_adapters.py` 寫一個工廠函式 `build_skill_tools(declarations: list[FunctionDeclaration]) -> list[FunctionTool]`:

```python
def build_skill_tools(declarations):
    tools = []
    for decl in declarations:
        params_schema = _gemini_to_openai_schema(decl.parameters)  # JSON Schema dialect 微調
        tools.append(FunctionTool(
            name=decl.name,
            description=decl.description,
            params_json_schema=params_schema,
            on_invoke_tool=lambda ctx, args, h=SKILL_HANDLERS[decl.name]: h(ctx=..., args=args),
        ))
    return tools
```

`_gemini_to_openai_schema` 處理:
- `type` 欄位從 enum object 轉成字串(`Type.OBJECT` → `"object"`)。
- `additionalProperties` 預設值修正(OpenAI schema strict mode 要求 `false`)。
- 巢狀 schema 遞迴處理。

**替代方案**:為每個 skill 手寫一個獨立 `FunctionTool`。**否決**:11 個工具樣板程式碼太多,且 `SKILL_DECLARATIONS` 已是真相源,複用最自然。

**理由**:工廠函式 ~30 行,handler dispatch 沿用既有 `SKILL_HANDLERS` 字典(完全不動)。預估總 LOC ~80–120,比 Google ADK 的 `SkillBaseTool` 子類路徑省。

### 4. Permission gate 透過 input guardrail 的 `reject_content` 模擬 deny

**選擇**:由於 OpenAI Agents SDK 沒有等價於 ADK `before_tool_callback` 的 hook,改在 **`on_invoke_tool` 包裝層**手動呼叫 `permission_gate.evaluate()`:

```python
def _wrap_with_permission_gate(handler, gate, tool_name):
    async def wrapped(ctx, args):
        decision = gate.evaluate(tool_name=tool_name, args=args, session_id=...)
        if decision.deny:
            return {
                "permission_denied": True,
                "reason": decision.reason,
                "tool": tool_name,
            }
        return await handler(ctx=..., args=args)
    return wrapped
```

回傳的 dict 會被 SDK Runner 當作 tool 正常 output 餵回模型,等於「deny 變成 synthetic tool_result」,對話不中斷。

`permission_gate.py` 同時新增 `as_openai_wrapper(gate: PermissionGate, tool_name: str) -> Callable`,封裝這個包裝邏輯。

**替代方案**:

- 用 SDK 的 input guardrail `reject_content`。**部分採用**:input guardrail 對「整個對話拒絕」夠用,但對「單一 tool deny」太粗;最後仍以 on_invoke_tool 包裝為主、guardrail 只做高階 policy。
- 用 `needs_approval` HITL 流程。**否決**:HITL 是同步阻塞等使用者批准,與本專案 deny → 模型自適應換路的 UX 不符。

**理由**:`on_invoke_tool` 包裝是 OpenAI Agents SDK 推薦的 per-tool 攔截路徑;與既有 `permission_gate` 語意對齊最直接。

### 5. Streaming 用 `Runner.run_streamed()` 的 `RunItem` / Raw events

**選擇**:`Runner.run_streamed()` 回傳 async iterator,事件包含:

| Event 類型 | 投影到 |
|---|---|
| `MessageOutputItem`(text delta)| SSE `stream_event` 增量推送 |
| `ToolCallItem` | SSE `tool_use` + `agent_messages` `tool_use` 寫入 |
| `ToolCallOutputItem` | SSE `tool_result` + `agent_messages` `tool_result` 寫入 |
| `RunCompleteEvent` | SSE 終態 + `agent_messages` `assistant`(彙總文字)寫入 |

**替代方案**:`Runner.run()` 非串流模式。**否決**:沒有 token-level 串流,使用者體驗倒退。

**理由**:既有 `gemini-full` 與 `claude` provider 都是 token-level 串流,維持 UX 一致。

### 6. UI 整合:runtime grid `openai × full` 解鎖

**選擇**:`AgentConfigTab.tsx` 中 `RUNTIME_MATRIX["openai"]["full"]` 從 `null` 改為 `"openai-full"`;`ASSISTANT_PROVIDER_META` 新增 `openai-full` 條目(label `OpenAI · 工作流模式`、tier `full`、description、requirement);`assistant.ts` 的 `ASSISTANT_PROVIDER_LABELS` 與 capability inference 也新增對應條目。

**理由**:現有 grid UI 已預留 OpenAI full 格(目前顯示為 disabled),只需把 null 改成新 provider id 即可解鎖,前端零新增元件。

## Risks / Trade-offs

- **[Risk] OpenAI Agents SDK API 仍在演進(v0.x 階段)** → Mitigation:`pyproject.toml` 鎖 minor(`openai-agents>=0.1,<0.2`,版本依 spike 階段確認結果);新建 `docs/openai-agents-upgrade-checklist.md`;CI 加版本探針。

- **[Risk] Schema 轉換不完整** → `FunctionDeclaration.parameters`(Google 風格)轉成 OpenAI JSON Schema dialect 時,可能有 `additionalProperties`、`type` enum、巢狀 ref 等差異。Mitigation:spike 階段對 7 個 skill 做 round-trip 測試,跑真實 GPT 模型驗證 tool call 行為與 Gemini 一致;不一致時調整 `_gemini_to_openai_schema`。

- **[Risk] Permission deny 行為不一致** → 包裝層在 `on_invoke_tool` 前攔截,但 SDK 內部可能對 dict return value 有特殊處理(例如自動加 `error` 包裝)。Mitigation:spike 必須對比 `gemini-full`(ADK) 與 `openai-full` 在相同 deny scenario 下的 canonical deny payload,確認 `permission_denied: true`、`reason`、`tool` 三個欄位 bit-for-bit 對齊。

- **[Trade-off] 每次 `Runner.run_streamed()` 餵完整歷史** → 長 session(>50 turns)會增加 prompt token 用量。**接受**:既有 `gemini-full` legacy 也是這個模式,不算回歸;後續可加歷史摘要層,但**不在本變更範圍**。

- **[Trade-off] 新增 `openai-agents` 依賴** → 鏡像體積、啟動時間增加。**接受**:OpenAI 使用者升到 full tier 的價值遠大於成本。

- **[Risk] `AssistantRuntimeProvider` 協議漂移** → 新 provider 加入時可能誘惑團隊把某家 SDK 特有概念寫進協議。Mitigation:Code review 守關;任何協議新增 method 必須三家都實作或全 default;不接受「只 openai-full 用」的 hook。

- **[Risk] `openai-lite` 與 `openai-full` 命名混淆** → 使用者可能不清楚差異。Mitigation:UI 標籤明確標 tier(`OpenAI · 對話模式` / `OpenAI · 工作流模式`),requirement 文案說明能力差異。

## Migration Plan

**Phase 0:準備(1 天)**

1. `pyproject.toml` 加 `openai-agents>=0.1,<0.2` 依賴;`uv sync` 驗證安裝。
2. 確認 `openai-agents` 與既有 `openai` SDK(在 `lib/openai_shared/` 等)無衝突。

**Phase 1:Spike(1.5 週)**

3. 實作 `openai_tool_adapters.py`:`_gemini_to_openai_schema()` 轉換器 + `build_skill_tools()` 工廠 + 11 個 FunctionTool 建立邏輯。
4. 對 7 個 skill 跑 round-trip schema 測試,確保 GPT 模型能正確解讀 tool calls。
5. 實作 `permission_gate.as_openai_wrapper()`,包裝 deny 邏輯。
6. 實作 `openai_full_runtime_provider.py` 主體:組裝 `Agent` + `Runner.run_streamed()`,實作 `_project_to_sse()` 把 events 投到既有 SSE buffer + `agent_messages` 寫入。
7. 實作 session_id 前綴 `openai-full:` 與 `infer_provider_id` 支援。
8. 寫測試:`test_openai_tool_adapters.py` 覆蓋 schema 轉換、`test_openai_full_runtime.py` 覆蓋 provider 主體(類比 `test_gemini_full_runtime.py` 的 80+ 案例結構)。

**Phase 2:整合(3 天)**

9. `service.py` 註冊新 provider。
10. 前端 `AgentConfigTab.tsx`:`RUNTIME_MATRIX["openai"]["full"]` 解鎖、`ASSISTANT_PROVIDER_META` 新增條目。
11. 前端 `assistant.ts`:capability inference + label 條目。
12. 端到端 smoketest:用 OpenAI provider 跑完整 manga 工作流(generate-script + generate-storyboard),對比輸出與 Gemini/Claude provider 行為一致。

**Phase 3:文件 + 上線(1 天)**

13. 更新 `CLAUDE.md`:`agent_runtime/` 模組清單新增 `openai_full_runtime_provider.py` 與 `openai_tool_adapters.py`;說明三家 full provider 都各自用各家 SDK。
14. CHANGELOG 記錄新增。
15. 預設 `ASSISTANT_PROVIDER` 不變(維持既有預設值),使用者主動切到 `openai-full` 才會走新路徑;不需 canary。

**回滾策略**

- 完全 opt-in:使用者不主動切到 `openai-full`,行為不受影響。
- 出問題:revert commit + 重新 deploy;舊 `openai-full` session 會無法繼續(但只有測試使用者會建立)。

## Open Questions

- 是否要在本變更內順便把 `openai-lite` 的串流補完(目前是 buffered 模式)?**暫不**,留待後續變更。
- OpenAI Agents SDK 的 tracing(Phoenix / Logfire 整合)是否要接到專案觀測系統?**Phase 3 之後評估**。
- 若 OpenAI Agents SDK v1.0 釋出且包含 breaking change,是否同步升級?**遵循 `docs/openai-agents-upgrade-checklist.md` 流程**,不自動跟版。
