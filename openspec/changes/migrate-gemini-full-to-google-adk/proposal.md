## Why

`gemini-full` 目前是手刻實作（`gemini_full_runtime_provider.py` 659 行 + `tool_sandbox.py` 245 行 + `permission_gate.py` 105 行 + `skill_function_declarations.py` 762 行，共 ~1770 LOC），自行維護工具循環、`generate_content_stream` chunk 解析、`functionCall` / `functionResponse` 配對、`thought_signature` 透傳等 Gemini 特有語意。Anthropic Claude provider 走官方 Claude Agent SDK，享有 SDK 維護紅利;Google 這邊卻長期承擔「等價於 Claude SDK 內部行為」的自研負擔。

Google 在 2025 年發布 **Gen AI Agent Development Kit (`google-adk`)** 作為 Gemini 官方的 agent 框架:內建 `Runner` 工具循環、`before_tool_callback` 權限鉤子、自動 streaming、tracing。本變更把 `gemini-full` 從原生 `google-genai` function calling 遷移到 `google-adk`,讓 Gemini 與 Claude 兩條 full-tier 路徑都對齊到「使用各家官方 agent SDK」的策略,回收約 250–350 行自維護程式碼(工具循環 + response parsing),並降低未來跟進 Gemini 新特性(live API、bidi streaming、Veo 整合)的維護成本。

## What Changes

- **新增** `GoogleAdkGeminiFullRuntimeProvider`(暫名 `adk_gemini_full_runtime_provider.py`):基於 `google.adk.Agent` + `Runner`,實作 `AssistantRuntimeProvider` 協議;`provider_id` 沿用 `gemini-full`,對外契約不變。
- **新增** `server/agent_runtime/adk_session_service.py`:實作 `BaseSessionService` 子類,把 ADK session events 映射到既有 `agent_messages` 表(`lib/db/models/agent_message.py`),避免雙 source-of-truth。
- **新增** 7 個 skill 的 `BaseTool` 子類介面卡,覆寫 `_get_declaration()` 直接複用 `skill_function_declarations.SKILL_DECLARATIONS` 中的手調 `FunctionDeclaration.parameters`,而非讓 ADK 從 Python signature 自動推導(保留現有 prompt-tuning 投資)。
- **修改** `permission_gate` 的整合路徑:從「provider 內部主迴圈手動呼叫」改為透過 ADK `before_tool_callback(tool, args, tool_context)` hook 注入;deny 時回傳 dict(ADK 跳過 tool 執行並把 dict 當 tool result 回 LLM),與既有「deny 不中斷對話」的語意一致。
- **修改** `server/agent_runtime/service.py` 的 `runtime_provider_registry`:`GEMINI_FULL_PROVIDER_ID` 改指向 `AdkGeminiFullRuntimeProvider`;舊 `GeminiFullRuntimeProvider` 直接刪除,出事透過 git revert 回滾(不引入 feature flag,避免把實作細節洩漏成使用者設定)。
- **保留** `tool_sandbox.py`(fs_read / fs_write / fs_list 白名單沙盒):ADK 不提供等價能力,業務邏輯全部留下,只是從「provider 主迴圈直接呼叫」變成「ADK BaseTool 子類內部呼叫」。
- **保留** `skill_function_declarations.py` 的 7 個 skill handler 業務邏輯:dispatch 框架由 ADK Runner 接手,但 handler 函式本體(generate-script、compose-video 等)一行不動,只是被新的 `BaseTool` 子類包裝。
- **新增** `pyproject.toml` 依賴 `google-adk>=1.32.0`。
- **BREAKING** 無對外 API 破壞。`provider_id`、SSE 事件 schema、`agent_messages` 表結構、前端 capability matrix 全部不變。

## Capabilities

### New Capabilities

無新增 capability。本變更僅替換 `gemini-full-runtime` 的實作底座,不引入新的對外契約。

### Modified Capabilities

- `gemini-full-runtime`:實作底座由「`google-genai` 原生 function calling + 自刻工具循環」改為「`google-adk` Agent + Runner」。spec-level 行為不變(capabilities tier、streaming、session 共用 `agent_messages` 表),但需補充:
  - SHALL 使用 `google-adk` 提供的 `Runner.run_async()` 作為工具循環引擎,不再自維護 `functionCall` / `functionResponse` 配對邏輯。
  - SHALL 透過 `before_tool_callback` 注入 `permission_gate`,deny 時回傳結構化 dict 而非中斷對話。
  - SHALL 實作 custom `BaseSessionService` 把 ADK session events 落到既有 `agent_messages` 表,禁用 ADK 內建的 `InMemorySessionService` / `DatabaseSessionService`。

- `assistant-tool-sandbox`:白名單規則與四個工具的輸入輸出契約**不變**,但需補充實作約束:
  - SHALL 把 `fs_read` / `fs_write` / `fs_list` / `run_subagent` 實作為 ADK `BaseTool` 子類,透過覆寫 `_get_declaration()` 保留現有手調 schema,而非使用 `FunctionTool` 的自動推導。

## Impact

**新增模組**
- `server/agent_runtime/adk_gemini_full_runtime_provider.py`:基於 ADK 的新 provider 主體。
- `server/agent_runtime/adk_session_service.py`:custom `BaseSessionService`,橋接 ADK session ↔ `agent_messages` 表。
- `server/agent_runtime/adk_tool_adapters.py`:7 個 skill 的 `BaseTool` 子類,加上 `fs_read` / `fs_write` / `fs_list` / `run_subagent` 的 `BaseTool` 包裝。

**修改模組**
- `server/agent_runtime/service.py`:`runtime_provider_registry` 直接註冊 `AdkGeminiFullRuntimeProvider` 取代舊 provider,不引入任何 env var 切換邏輯。
- `server/agent_runtime/permission_gate.py`:核心 policy 函式不動,新增 `as_adk_callback()` 介面卡函式回傳 ADK `before_tool_callback` 相容簽名。
- `server/agent_runtime/skill_function_declarations.py`:handler 函式保留;`SKILL_DECLARATIONS` 列表變成 `adk_tool_adapters` 的輸入資料源。
- `server/agent_runtime/tool_sandbox.py`:核心沙盒邏輯保留;新增 ADK `BaseTool` 包裝層;`FS_READ_DECLARATION` / `FS_WRITE_DECLARATION` / `FS_LIST_DECLARATION` 三個常量從舊 provider 搬過來作中性常量。

**刪除**
- `server/agent_runtime/gemini_full_runtime_provider.py` 整檔(包含 `_run_generation` 工具循環、`_handle_function_call` chunk parsing、`_format_functionResponse` 包裝等共約 600+ 行)。
- `tests/test_gemini_full_runtime.py`(legacy provider 的單元測試,核心 case 已由 `tests/test_adk_gemini_full_runtime.py` 涵蓋)。

**依賴**
- 新增 `google-adk>=1.32.0`(含傳遞依賴 `opentelemetry-*`、`pydantic`、`google-cloud-aiplatform` 等)。
- 不影響現有 `google-genai` 依賴(lib/gemini_shared/、lib/text_backends/、lib/video_backends/ 仍直接使用)。

**資料庫**
- `agent_messages` 表 schema 不變。
- 必須保證 ADK 的 session event 序列能完整映射到既有 message type(`tool_use` / `tool_result` / `permission_decision` / `text` / `thinking`),否則舊 session 重放會失敗。

**風險**
- **`google-adk` 雙週發版(截至 1.32.0),breaking change 風險高**:遷移完成後需建立版本鎖定策略與升級 PR 範本,避免被動跟版。
- **7 skill schema adapter 程式碼量是否真的省**:spike 階段必須實測比對 — 如果每個 skill 寫一個 `BaseTool` 子類比現有 `FunctionDeclaration` 轉換還多程式碼(dataclass + 覆寫 `_get_declaration` + `run_async`),整個遷移取消。
- **ADK live streaming 標記 experimental**:v0.5.0 文件明示 `Runner.run_live()` experimental;本次遷移先用 `Runner.run_async()`(事件流),不引入 bidi streaming。
- **回歸風險**:現有 `tests/test_gemini_full_runtime.py` 覆蓋現狀的 80+ 案例核心行為已由 `tests/test_adk_gemini_full_runtime.py` 移植;新增 `tests/test_adk_session_service.py` 覆蓋 session 橋接邊界。
- **回滾策略**:不引入 feature flag,改採「直接切換 + git revert」。Phase 2 部署到 staging 7 天觀察 SSE 錯誤率與 `agent_messages` 寫入;若有 P1 問題則 revert commit + redeploy。

**對外 API**
- 公開 HTTP API、SSE 事件 schema、capability matrix、session_id 前綴全部不變。
- 前端 `AgentCopilot` / `AgentConfigTab` / `useAssistantSession` **零改動**。
