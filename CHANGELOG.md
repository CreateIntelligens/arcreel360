# Changelog

本檔記錄 ArcReel 360 相對原始 ArcReel 專案的重要差異與維護脈絡。

### 劇集預處理、任務佇列與文件同步

- **README 對齊目前 runtime 現況**：將 assistant provider 說明從早期的 `Claude full + Gemini Lite + OpenAI Lite` 更新為 `Claude full + Gemini Lite/Full + OpenAI Lite/Full`，並把 `workflow-grade` 改寫為設計語彙，而非使用者可選的第三種 provider tier。
- **CLAUDE.md 架構說明同步**：補上 `episode_splitter.py`、Step 1 預處理原文解析優先序、任務 SSE 與排隊任務取消規則，避免 agent 依舊文件誤判路由與資料流。
- **說書模式自動均分原文**：`narration` Step 1 在缺少 `source/episode_N.txt` 時，會串接 `source/` 下原文檔並依 `project.json.episodes` 均分取該集；使用者仍可指定 `source` 覆寫。
- **指定原文入口**：前端劇集 actions bar 新增「指定原文」下拉，列出 `source/` 下可用文字檔，讓使用者能用特定原文檔重新拆段或規範化。
- **任務取消體驗**：任務 HUD 支援取消單一排隊任務、預覽依賴任務級聯取消，以及取消專案內所有排隊任務；後端任務狀態新增 `cancelled` 與 `cancelled_by`。

### Gemini Full ADK 遷移與架構收尾

將 `gemini-full` runtime 從原生 `google-genai` function calling 遷移至 Google ADK (`google-adk`) 框架，提升工具循環的穩定性與擴展性。

- **ADK 遷移**：新增 `adk_gemini_full_runtime_provider.py`，使用 `google.adk.Runner` 作為核心引擎，替換手動維護的 `_run_generation` 工具循環。
- **架構優化**：
  - **安全性**：`permission_gate` 透過 `as_adk_callback` 整合至 ADK tool loop，支援 PreToolUse 風格的攔截與錯誤回傳。
  - **持久化**：使用 `AgentMessagesSessionService` (ADK 版) 進行資料庫備份的 session 訊息持久化，與專案既有的 `agent_messages` 模式完美對齊。
  - **一致性**：通過一致性測試 (`test_consistency.py`) 驗證 ADK 版本輸出的 SSE 事件流與舊版完全一致，確保前端無感遷移。
- **清理**：刪除舊版 `gemini_full_runtime_provider.py` 及相關遺留測試，將單元測試遷移至 `test_gemini_full_runtime.py`。
- **Smoketest**：更新 `scripts/gemini_full_smoketest.py` 支援 `--mock` 模式，便於在無 API key 環境下驗證工具鏈完整性。

新增 `gemini-full` 執行階段供應商作為 Claude 之外的第二個 full-tier runtime，並補齊周邊基礎設施與已知缺陷。

- **新 runtime**：`server/agent_runtime/` 加入 `gemini_full_runtime_provider.py`（Gemini function calling 工具循環）、`tool_sandbox.py`（白名單 fs_read / fs_write / fs_list）、`permission_gate.py`（PreToolUse 風格權限閘門）、`skill_function_declarations.py`（7 個 skill → FunctionDeclaration 翻譯與 dispatch）。目前與 `claude`、`gemini-lite`、`openai-lite`、`openai-full` 並列為五個可切換 runtime，由 `ASSISTANT_PROVIDER` 環境變數或 `system_setting.assistant_provider` 決定。
- **持久化**：新增 `agent_messages` 表（migration `a1b2c3d4e5f6`）作為跨 provider 的訊息持久化共用欄位，tool_use / tool_result 在此寫入以利 SSE 重放。
- **資料契約**：`turn_schema.normalize_block()` 統一將 `tool_result.content` / `tool_use.result` / `skill_content` 序列化為字串。先前後端工具回傳 dict（如 `fs_write` 的 `{bytes_written, created}`）會直接被前端當 React child 渲染並觸發 React error #31；序列化集中在後端出口處理後，所有 turn_grouper / stream_projector 路徑收尾都會經過。前端 `ContentBlockRenderer` 補上 defense-in-depth stringify。
- **Skill subprocess 環境**：`compose_video` skill 透過 subprocess 執行時，`cwd` 切到 project 目錄後 sys.path 不再包含 repo root，導致 `from lib.project_manager import ...` 失敗。`skill_function_declarations._handle_compose_video` 在 spawn 時注入 `PYTHONPATH=<repo_root>`。
- **效能**：`gemini-full` 的 `genai.Client` 改為依設定 key 快取，重複對話不再每輪重建；Vertex 模式憑證檔讀取改走 `asyncio.to_thread`，不再阻塞事件迴圈。`AssistantService.list_sessions()` 新增 per-provider capabilities 快取，避免大量 session 時重複呼叫 `model_dump()`。
- **影片生成**：`veo-3.1-lite-generate-preview` 等 Veo lite 變體 API 拒收 `negativePrompt`，後端 `GeminiVideoBackend` 依 model 名稱判斷是否帶上該欄位避免 400；同步將 registry 中該 model 的 `negative_prompt` capability 移除，與實際 API 行為對齊。
- **供應商設定一致性**：預置 OpenAI 連線測試補上 `ensure_openai_base_url()` 正規化，與自定義 provider 路徑一致，使用者填 `https://api.example.com`（缺 `/v1`）也能正確驗證。
- **助理面板**：`AgentCopilot` / `AgentConfigTab` 新增 provider × tier 二維選擇器與能力提示；移除 Claude 專屬 icon 改用中性 `Bot`，「API 憑證 / 模型設定」兩段僅在實際選擇 Claude 時才顯示，使用 Gemini／OpenAI 不再被 Anthropic 設定洗版。`useAssistantSession` 重寫流式狀態收斂以支援 capability 矩陣。
- **對話 UX**：新增 `ToolCallGroup`，同一 turn 內連續 ≥2 個非 TodoWrite 的 `tool_use` 自動摺成可展開群組，header 顯示「工具呼叫 N 次／完成數／狀態」，避免 generate 類工作流多步呼叫洗版。
- **測試**：新增 80+ 案例覆蓋上述新模組（`test_gemini_full_runtime.py`、`test_tool_sandbox.py`、`test_permission_gate.py`、`test_skill_function_declarations.py`、`test_turn_grouper_gemini_full.py`）。

### OpenAI Full Assistant Runtime

- **新 runtime**：新增 `openai-full`，基於 OpenAI Agents SDK (`openai-agents`) 實作 full-tier 工具循環，與 `openai-lite` 純對話路徑並存。`AssistantService` registry、`openai-full:` session routing、capabilities 與 system config 允許清單已補齊。
- **工具介面卡**：新增 `openai_tool_adapters.py`，將 7 個 ArcReel skill 與 `fs_read` / `fs_write` / `fs_list` / `run_subagent` 包成 11 個 OpenAI `FunctionTool`，直接複用既有手調 schema 並轉成 strict JSON Schema。
- **權限一致性**：`permission_gate.as_openai_wrapper()` 將 deny 包成 canonical tool_result payload（`permission_denied: true`、`reason`、`tool`），並與 `gemini-full`(ADK) 形狀對齊。
- **設定頁**：OpenAI × 工作流模式在 provider grid 解鎖，新增「OpenAI · 工作流模式」標籤與 capability 說明；grid 改用固定欄寬 CSS grid，修正三家 provider 欄位視覺對齊。
- **測試**：新增 `test_openai_full_runtime.py`、`test_openai_tool_adapters.py` 與 `frontend/src/types/assistant.test.ts`，覆蓋工具 schema、Runner stream 投影、歷史重放、中斷、heartbeat timeout、OpenAI/Gemini deny payload 一致性與前端 provider inference。

### 部署

- 新增 `docker-compose.yml` 與重寫的 `Dockerfile`（multi-stage `builder → runner`），將原本臨時的 `docker run` 命令收斂到 compose orchestration；擴充 `.env.example` 與 `.gitignore` 對應本地 compose 部署所需變數。

### 文案／文件

- 將 350+ 個檔案（測試、後端、前端、skills、workflows、文件）全面繁體化，使整個專案的內部與外部文案一致。
- 更新 `CLAUDE.md` 反映多 provider runtime、tool_result 字串化契約等變更；`AGENTS.md` 改為指向 `CLAUDE.md` 的 symlink，避免兩份檔再度 drift。

## 2026-04-30

### 繁體版本定位強化

- 在 README 首屏明確標示：ArcReel 360 是 ArcReel 的繁體中文 fork。
- 補上更直接的語系定位說明，讓外部讀者第一眼就知道這不是 upstream 的簡體中文倉庫。
- 將「繁體中文」從單純檔案描述，提升為 fork 的對外定位與維護承諾。

### 檔案與產品呈現方向

- README 新增更高可見度的繁體中文版本宣告與語系策略說明。
- 明確說明本 fork 的產品顯示文案將持續朝繁體中文收斂。
- 保持與 upstream 的區隔：原版仍可參考 upstream，本倉庫則明確面向繁體中文使用者與二開場景。

## 2026-04-29

### Fork 定位

- 建立 ArcReel 360 的 fork 敘事與繁體中文檔案方向。
- README 改為以 fork、二開、多 provider assistant 為核心，而不是延續 upstream 的單一路徑描述。
- 明確標示新倉庫網址：<https://github.com/CreateIntelligens/arcreel360>
- 明確致謝原作者與原始 ArcReel 專案：<https://github.com/ArcReel/ArcReel>

### Assistant Runtime

- 將 assistant runtime 從 Claude 專屬路徑抽象為多 provider runtime。
- 保留 Claude 作為 `full` provider。
- 新增 Gemini Lite provider。
- 新增 OpenAI Lite provider。
- session / snapshot / status / 同步 chat API 現在可暴露 provider 與 capability 資訊。

### Frontend 與配置語意

- 系統設定頁新增 assistant provider 選擇。
- 將 Anthropic 從全域硬性必填改為 Claude provider 的 provider-specific requirement。
- Gemini-only 與 OpenAI-only 場景不再因缺少 Anthropic 被誤判為設定未完成。
- assistant 面板改為依 capability matrix 隱藏或禁用不支援功能。

### 部署與穩定性

- 補回缺失的 Alembic migration，恢復部署資料庫的 revision 鏈。
- 修正多 provider runtime 與既有 app startup 的相容性，補回 `start_patrol()` 啟動路徑。
- 重新建置 Docker image 並完成容器替換，確認 `/health` 正常回應。

### 自定義供應商與穩定性補強

- 新增 `lib/custom_provider/`（`backends.py`、`discovery.py`、`factory.py`）與 `server/routers/custom_providers.py`：使用者可自行新增 OpenAI／Google 相容供應商，附帶模型發現、連線測試、每模型 default/enabled 開關與 OpenAI／Google 雙 API 格式分流。
- 新增 `CustomProvider` / `CustomProviderModel` ORM 模型與 Repository、`CustomProviderForm` / `CustomProviderDetail` / `CustomProviderSection` 三個前端頁面，整合到既有 Provider Settings 路由。
- 新增 Alembic migration `0a1b2c3d4e5f_restore_custom_provider_compat_columns.py` 修正欄位相容性。
- `ProviderSection` 補上錯誤處理與 loading 邊界、加上對應 unit tests。

### 與原作者版本的摘要差異

| 面向 | 原作者版本 | ArcReel 360 |
| --- | --- | --- |
| Assistant 核心設計 | Claude runtime 為中心 | 多 provider runtime 為中心 |
| 可用 assistant | Claude | Claude、Gemini Lite/Full、OpenAI Lite/Full |
| 配置判定 | Anthropic 容易被視為全域必填 | 改為依目前 provider 判定 |
| 前端能力假設 | 預設 provider 能力完整一致 | 顯式 capability 降級 |
| 檔案語系 | 簡體中文為主 | 繁體中文為主 |
| 二開定位 | 偏 upstream 原始產品敘事 | 偏 fork 維護與可二開性 |
