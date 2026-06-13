## Why

目前三家供應商在 ArcReel 助理執行階段裡的 tier 不對等:

| Provider | Tier | 工具循環 | 來源 |
|---|---|---|---|
| `claude` | full | ✅ Claude Agent SDK | Anthropic 官方 |
| `gemini-full` | full | ✅ 自刻 / 預計遷移到 Google ADK | (見 `migrate-gemini-full-to-google-adk`) |
| `gemini-lite` | lite | ❌ 純對話 | google-genai 文字後端 |
| `openai-lite` | lite | ❌ 純對話 | openai 文字後端 |

OpenAI 使用者目前**完全無法**跑漫畫工作流(generate-script、generate-storyboard 等),只能拿來純聊天。OpenAI 在 2025 年發布了 **OpenAI Agents SDK** (`openai-agents-python`),內建 `Agent` / `Runner` / `FunctionTool` / guardrails / streaming,且 **`FunctionTool(params_json_schema=...)` 可直接吃手調 schema**(不像 Google ADK 強制 signature 推導),session 也是 opt-in(可繞過內建,直接用 `Runner.run(input=[...])`)。

本變更新增 `openai-full` provider,把 OpenAI 升到 full tier:讓使用者也能用 GPT 模型完整跑工作流;同時把 ArcReel 的策略補完成「三家 full-tier provider 各自使用各家官方 agent SDK」的對稱結構。

## What Changes

- **新增** `OpenAIFullRuntimeProvider`(暫名 `openai_full_runtime_provider.py`):基於 `openai_agents.Agent` + `Runner`,實作 `AssistantRuntimeProvider` 協議;`provider_id` 為 `openai-full`;capabilities tier 為 `full`,`supports_tool_calls` / `supports_subagents` / `supports_resume` / `supports_permission_hooks` 全部為 `true`。
- **新增** `server/agent_runtime/openai_tool_adapters.py`:把既有 7 個 skill 與 4 個 fs 工具(共 11 個)包成 `FunctionTool(name, description, params_json_schema, on_invoke_tool)`,**直接複用** `SKILL_DECLARATIONS` 中的 `FunctionDeclaration.parameters`(轉成 OpenAI JSON Schema 格式),保留現有 prompt-tuning 投資。
- **新增** Permission gate 的 OpenAI Agents SDK 整合路徑:由於 OpenAI Agents SDK 沒有等價 `before_tool_callback`,改用 **input guardrail 的 `reject_content`** 模擬「deny → 包成 synthetic tool_result 回模型,不中斷對話」的語意。
- **新增** Session id 前綴 `openai-full:`(沿用 `build_external_session_id` 模式);session 持久化**直接複用** `agent_messages` 表,不實作 `BaseSessionService` 等價物 —— 而是每次 `Runner.run_streamed(input=[既有歷史], ...)` 餵完整 history list,把 SDK 的 stream events 投影回 `agent_messages` 寫入。
- **新增** Streaming 投影:`Runner.run_streamed()` 產出 `RunItem` / `RawResponseStreamEvent`,系統 MUST 把 text delta、tool_called、tool_output 投影到既有 SSE buffer 與 `agent_messages` 表。
- **修改** `server/agent_runtime/service.py` 的 `runtime_provider_registry`:新增 `OPENAI_FULL_PROVIDER_ID = "openai-full"`,註冊新 provider;`_resolve_active_provider_id` 接受新值。
- **修改** `frontend/src/components/pages/AgentConfigTab.tsx` 的 runtime grid:`openai × full` 從 `null` 改為 `"openai-full"`,使用者可在 UI 選到「OpenAI · 工作流模式」。
- **修改** `frontend/src/types/assistant.ts`:`ASSISTANT_PROVIDER_LABELS` 新增 `openai-full`,`inferAssistantProvider` 支援 `openai-full:` 前綴。
- **新增** `pyproject.toml` 依賴 `openai-agents>=0.1.0`(版本待 spike 確認)。
- **保留** `openai-lite` 不動:純對話、無工具、不依賴 openai-agents SDK,維持現狀。
- **BREAKING** 無對外 API 破壞。`gemini-lite` / `gemini-full` / `openai-lite` / `claude` 全部行為不變。

## Capabilities

### New Capabilities

- `openai-full-runtime`:定義 OpenAIFullRuntimeProvider 的對外契約 —— capabilities 等級、OpenAI Agents SDK 工具循環、流式行為、`agent_messages` 表共用策略、Session id 前綴、與 `openai-lite` 的切換邊界。

### Modified Capabilities

- `assistant-runtime-selection`:前端 runtime grid 新增 `openai × full` 組合;`ASSISTANT_PROVIDER` env var 與 `assistant_provider` 系統設定接受新值 `openai-full`;capability matrix 資料流不變。

- `assistant-tool-sandbox`:既有白名單規則與四個 fs 工具的輸入輸出契約**不變**,但需補充實作約束 —— 在 `openai-full` provider 中,fs 工具 MUST 包裝為 `openai_agents.FunctionTool`,`params_json_schema` 直接複用 `SKILL_DECLARATIONS` 中的對應 schema(轉換為 OpenAI JSON Schema dialect)。

- `workflow-orchestration`:現有規格本身就是 provider-agnostic 的(要求 manga-workflow skill 偵測專案狀態並 dispatch 對應 subagent,不限定 LLM 來源)。新 provider 只要忠實實作 skill 協議即可,**無需修改 spec-level requirements**。

## Impact

**新增模組**
- `server/agent_runtime/openai_full_runtime_provider.py`:基於 OpenAI Agents SDK 的 provider 主體。
- `server/agent_runtime/openai_tool_adapters.py`:11 個 `FunctionTool` instance(7 個 skill + 4 個 fs 工具),`params_json_schema` 來源為 `SKILL_DECLARATIONS`。
- `tests/test_openai_full_runtime.py`:provider 整合測試。
- `tests/test_openai_tool_adapters.py`:tool 介面卡單元測試,驗證 schema 與 `SKILL_DECLARATIONS` 對齊。

**修改模組**
- `server/agent_runtime/service.py`:`runtime_provider_registry` 註冊新 provider。
- `server/agent_runtime/session_identity.py`:新增 `OPENAI_FULL_PROVIDER_ID = "openai-full"` 與 `openai-full:` 前綴;`infer_provider_id` 支援。
- `server/agent_runtime/permission_gate.py`:核心 policy 不動;新增 `as_openai_guardrail(gate: PermissionGate) -> Callable` 介面卡函式回傳 OpenAI Agents SDK input guardrail 簽名。
- `frontend/src/components/pages/AgentConfigTab.tsx`:`RUNTIME_MATRIX["openai"]["full"]` 從 `null` 改為 `"openai-full"`。
- `frontend/src/types/assistant.ts`:`ASSISTANT_PROVIDER_LABELS` 新增 `openai-full`;capability inference 支援。
- `frontend/src/components/pages/AgentConfigTab.tsx` 的 `ASSISTANT_PROVIDER_META` 新增 `openai-full` 條目(label、tier=full、description、requirement)。

**依賴**
- 新增 `openai-agents>=0.1.0`(含傳遞依賴,spike 階段確認版本範圍)。
- 不影響既有 `openai` SDK 依賴(`lib/openai_shared/`、`lib/text_backends/openai.py` 仍直接使用,`openai-lite` 不動)。

**資料庫**
- `agent_messages` 表 schema 不變。
- session_id 前綴新增 `openai-full:`;`agent_messages.message_type` 列舉複用既有 `tool_use` / `tool_result` / `text` / `thinking` / `result`,無新增。

**外部 API**
- 公開 HTTP API、SSE 事件 schema 不變。
- 前端 capability matrix 增加 `openai-full` 條目,但結構不變(`{provider, tier, capabilities: {...}}`)。

**風險**
- **OpenAI Agents SDK 版本穩定度**:SDK 在 2025 釋出後仍在快速演進,API surface 可能 breaking。Mitigation:鎖 minor 版本(`>=0.1,<0.2`),建立升級檢查清單(類似 `docs/adk-upgrade-checklist.md`)。
- **input guardrail 模擬 deny 行為的精確度**:OpenAI Agents SDK 沒有 ADK / Anthropic SDK 等價的 `before_tool_callback`。`reject_content` 是針對 input 階段的 guardrail,模擬「deny tool 後包成 synthetic tool_result」需要在 SDK runner 外層手動攔截;spike 階段必須驗證行為與既有 `permission_gate` 語意 1:1 對齊,不可有「deny 後對話被中斷」的回歸。
- **Schema 轉換可能不完整**:Google `FunctionDeclaration.parameters` 與 OpenAI JSON Schema 略有差異(例如 `type: "object"` vs `type: ["object"]`、`additionalProperties` 預設值)。spike 必須做 round-trip 測試,確認轉換後的 schema 能讓 GPT 模型產生與 Gemini 行為一致的 tool calls。
- **SDK 內建 session 與我們的 `agent_messages` 共存**:SDK Runner 雖支援 `Runner.run(input=[...])` 繞過內建 session,但若不慎打開 session memory 功能會造成雙真相源。Mitigation:在 provider 主體明確 `session=None`,加入 unit test 確保不會被誤觸發。
- **多 provider 抽象漂移風險**:本變更引入第三家 SDK 後,`AssistantRuntimeProvider` 協議必須繼續維持夠通用,避免哪家 SDK 特有概念洩漏到介面。Mitigation:任何介面新增方法/欄位,必須三家都實作或全 default;不接受「只 openai-full 用」的 hook。
- **使用者切換時的命名混淆**:UI 上同時出現 `openai-lite`(對話模式)與 `openai-full`(工作流模式),需確保前端文案明確區分(沿用既有 `tier` 標籤)。
