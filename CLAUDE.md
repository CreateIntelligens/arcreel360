# Repository Guidance

> 此檔同時被 `CLAUDE.md`（Claude Code）與 `AGENTS.md`（Codex 等）讀取 — `AGENTS.md` 是指向本檔的 symlink，請只在 `CLAUDE.md` 編輯。

This file provides guidance to coding agents (Claude Code, Codex, etc.) when working with code in this repository.

## 語言規範
- **回答使用者必須使用繁體中文**：所有回覆、任務清單及計劃檔案，均須使用繁體中文；除非使用者明確要求翻譯或輸出其他語言，否則不要使用簡體中文或英文作為主要回覆語言

## 專案概述

ArcReel 是一個 AI 影片生成平臺，將小說轉化為短影片。三層架構：

```
frontend/ (React SPA)  →  server/ (FastAPI)  →  lib/ (核心庫)
  React 19 + Tailwind       路由分發 + SSE        多 provider 媒體後端
  wouter 路由               agent_runtime/        GenerationQueue
  zustand 狀態管理          (多 provider runtime)  ProjectManager
```

## 開發命令

```bash
# 後端
uv run python -m pytest                              # 測試（-v 單檔案 / -k 關鍵字 / --cov 覆蓋率）
uv run ruff check . && uv run ruff format .          # lint + format
uv sync                                              # 安裝依賴
uv run alembic upgrade head                          # 資料庫遷移
uv run alembic revision --autogenerate -m "desc"     # 生成遷移

# 前端（cd frontend &&）
pnpm build       # 生產構建 (含 typecheck)
pnpm check       # typecheck + test
```

## 架構要點

### 後端 API 路由

所有 API 在 `/api/v1` 下，路由定義在 `server/routers/`：
- `projects.py` — 專案 CRUD、概述生成
- `generate.py` — 分鏡/影片/角色/線索生成（入隊到任務佇列）
- `assistant.py` — 跨 provider 助理會話管理（SSE 流式，依 `assistant_provider` 路由到對應 runtime）
- `agent_chat.py` — 智慧體對話互動
- `tasks.py` — 任務佇列狀態、SSE 流式、排隊任務取消
- `project_events.py` — 專案事件 SSE 推送
- `files.py` — 檔案上傳與靜態資源
- `versions.py` — 資源版本歷史與回滾
- `characters.py` / `clues.py` — 角色/線索管理
- `usage.py` — API 用量統計
- `cost_estimation.py` — 費用預估（專案/單集/單鏡頭）
- `auth.py` / `api_keys.py` — 認證與 API 金鑰管理
- `system_config.py` — 系統配置
- `providers.py` — 預置供應商配置管理（列表、讀寫、連線測試）
- `custom_providers.py` — 自定義供應商 CRUD、模型管理與發現、連線測試

### server/services/ — 業務服務層

- `generation_tasks.py` — 分鏡/影片/角色/線索生成任務編排
- `project_archive.py` — 專案匯出（ZIP 打包）
- `project_events.py` — 專案變更事件釋出
- `jianying_draft_service.py` — 剪映草稿匯出
- `cost_estimation.py` — 費用預估計算與實際費用匯總

### lib/ 核心模組

- **{gemini,ark,grok,openai}_shared** — 各供應商 SDK 工廠與共享工具
- **image_backends/** / **video_backends/** / **text_backends/** — 多供應商媒體生成後端，Registry + Factory 模式（gemini/ark/grok/openai）
- **custom_provider/** — 自定義供應商支援：後端包裝、模型發現、工廠建立（OpenAI/Google 相容）
- **MediaGenerator** (`media_generator.py`) — 組合後端 + VersionManager + UsageTracker
- **GenerationQueue** (`generation_queue.py`) — 非同步任務佇列，SQLAlchemy ORM 後端，lease-based 併發控制
- **GenerationWorker** (`generation_worker.py`) — 後臺 Worker，分 image/video 兩條併發通道
- **episode_splitter** (`episode_splitter.py`) — 原文分集切分、自然斷點搜尋、說書模式自動按集數均分
- **ProjectManager** (`project_manager.py`) — 專案檔案系統操作和資料管理
- **StatusCalculator** (`status_calculator.py`) — 讀時計算狀態欄位，不儲存冗餘狀態
- **UsageTracker** (`usage_tracker.py`) — API 用量追蹤
- **CostCalculator** (`cost_calculator.py`) — 費用計算
- **TextGenerator** (`text_generator.py`) — 文字生成任務
- **retry** (`retry.py`) — 通用指數退避重試裝飾器，各供應商後端複用

### lib/config/ — 供應商配置系統

ConfigService（`service.py`）→ Repository（持久化 + 金鑰脫敏）→ Resolver（解析）。`registry.py` 維護預置供應商登錄檔（PROVIDER_REGISTRY）。

### lib/db/ — SQLAlchemy Async ORM 層

- `engine.py` — 非同步引擎 + session factory（`DATABASE_URL` 預設 `sqlite+aiosqlite`）
- `models/` — ORM 模型：Task / ApiCall / ApiKey / AgentSession / Config / Credential / User / CustomProvider / CustomProviderModel
- `repositories/` — 非同步 Repository：Task / Usage / Session / ApiKey / Credential / CustomProvider

資料庫檔案：`projects/.arcreel.db`（開發 SQLite）

### Agent Runtime（多 provider 助手執行時）

`server/agent_runtime/` 統一管理多個 assistant provider，由 `ASSISTANT_PROVIDER` 環境變量或 DB `system_setting.assistant_provider` 切換：

| provider id | 模式 | tier | 說明 |
|---|---|---|---|
| `gemini-lite`（預設） | 對話 | lite | 純文字流式對話，走 `lib/text_backends/gemini.py` |
| `gemini-full` | 工作流 | full | Google ADK 工具循環，可呼叫 fs_*/skill 自動化生成 |
| `openai-lite` | 對話 | lite | 對應 OpenAI 文字後端 |
| `openai-full` | 工作流 | full | OpenAI Agents SDK 工具循環，可呼叫 fs_*/skill 自動化生成 |
| `claude` | 工作流 | full | Claude Agent SDK，bundled CLI + OAuth 登入態 |

核心模組：
- `service.py` `AssistantService` — 編排 + provider registry + capabilities 注入
- `text_backend_runtime_provider.py` — lite providers（純對話）+ session lifecycle 基類
- `adk_gemini_full_runtime_provider.py` — Google ADK 版 `gemini-full` 工具循環
- `openai_full_runtime_provider.py` — OpenAI Agents SDK 版 `openai-full` 工具循環
- `openai_tool_adapters.py` — 既有 7 個 skill + 4 個 fs 工具轉成 OpenAI `FunctionTool`
- `tool_sandbox.py` — 白名單沙盒（fs_read/fs_write/fs_list）
- `permission_gate.py` — PreToolUse 風格權限閘門（ADK / OpenAI wrapper 共用 canonical deny payload）
- `skill_function_declarations.py` — 7 個 skill → Gemini FunctionDeclaration 翻譯與 dispatch
- `session_manager.py` — Claude SDK session 管理（僅 claude provider 用）
- `stream_projector.py` — 從流式事件構建實時助手回覆

session 訊息持久化：`agent_messages` 表（`lib/db/models/agent_message.py`），所有 provider 共用。tool_use / tool_result message 由 full-tier providers 寫入。

切換 provider 後，新建會話走新 provider（session id 前綴決定路由），舊 session 仍走原 provider 讀歷史。

**Tool result 字串化契約**：`tool_result.content` / `tool_use.result` / `skill_content` 在出口必須是 string（前端 `<pre>{value}</pre>` 直接渲染）。`turn_schema.normalize_block()` 集中處理 — 後端工具回傳 dict（如 `fs_write` 的 `{bytes_written, created}`）會在此自動 `json.dumps` 序列化。`turn_grouper` 與 `stream_projector` 兩條路徑收尾都呼叫 `normalize_turn`，所以新增 skill handler 不必自行 stringify。

### 前端

- React 19 + TypeScript + Tailwind CSS 4
- 路由：`wouter`（非 React Router）
- 狀態管理：`zustand`（stores 在 `frontend/src/stores/`）
- 路徑別名：`@/` → `frontend/src/`
- Vite 代理：`/api` → `http://127.0.0.1:1241`

## 關鍵設計模式

### 資料分層

| 資料型別 | 儲存位置 | 策略 |
|---------|---------|------|
| 角色/線索定義 | `project.json` | 單一真相源，劇本中僅引用名稱 |
| 劇集後設資料（episode/title/script_file） | `project.json` | 劇本儲存時寫時同步 |
| 統計欄位（scenes_count / status / progress） | 不儲存 | `StatusCalculator` 讀時計算注入 |

### 劇集 Step 1 預處理

`lib/episode_preprocess.py` 依 `project.json.content_mode` 呼叫 agent profile 內的 Step 1 腳本：

- `narration` → `split_narration_segments.py`，輸出 `drafts/episode_N/step1_segments.md`
- `drama` → `normalize_drama_script.py`，輸出 `drafts/episode_N/step1_normalized_script.md`

原文解析優先序：

1. 使用者指定 `source` 時，讀取該專案內檔案；可用逗號分隔多檔，依序讀取串接（`narration`／`drama` 行為一致）。
2. 存在 `source/episode_N.txt` 時，優先使用手動精切檔。
3. `narration` 模式缺專屬檔時，串接 `source/` 內文字檔（排除 `_remaining.txt` 與 `episode_N.*`），再依 `project.json.episodes` 數量均分取該集。
4. `drama` 規範化模式缺專屬檔時，目前直接使用串接後的整本原文。

### 實時通訊

- 助手：`/api/v1/assistant/sessions/{id}/stream` — SSE 流式回覆
- 專案事件：`/api/v1/projects/{name}/events/stream` — SSE 推送專案變更
- 任務佇列：`/api/v1/tasks/stream` — SSE 推送 snapshot / task 事件；`/api/v1/tasks` 仍可查詢列表

### 任務佇列

所有生成任務（分鏡/影片/角色/線索）統一透過 GenerationQueue 入隊，由 GenerationWorker 非同步處理。
`generation_queue_client.py` 的 `enqueue_and_wait()` 封裝入隊 + 等待完成。
任務狀態包含 `queued` / `running` / `succeeded` / `failed` / `cancelled`；取消只允許排隊中任務，依賴任務會以 `cancelled_by="cascade"` 標記級聯取消。

### Pydantic 資料模型

`lib/script_models.py` 定義 `NarrationSegment` 和 `DramaScene`，用於劇本驗證。
`lib/data_validator.py` 驗證 `project.json` 和劇集 JSON 的結構與引用完整性。

## 智慧體執行環境

智慧體專用配置（skills、agents、系統 prompt）位於 `agent_runtime_profile/` 目錄，
與開發態 `.claude/` 物理分離。

### Skill 維護

```bash
# 觸發率評估（需要 anthropic SDK：uv pip install anthropic）
PYTHONPATH=~/.claude/plugins/cache/claude-plugins-official/skill-creator/*/skills/skill-creator:$PYTHONPATH \
  uv run python -m scripts.run_eval \
  --eval-set <eval-set.json> \
  --skill-path agent_runtime_profile/.claude/skills/<skill-name> \
  --model sonnet --runs-per-query 2 --verbose
```

#### Gotchas

- **SKILL.md 與指令碼同步**：修改 skill 指令碼時需同步更新 SKILL.md，反之亦然，二者必須保持一致

## 環境配置

複製 `.env.example` 到 `.env`，設定認證引數（`AUTH_USERNAME`/`AUTH_PASSWORD`/`AUTH_TOKEN_SECRET`）。
API Key、後端選擇、模型配置等透過 WebUI 配置頁（`/settings`）管理。
外部工具依賴：`ffmpeg`（影片拼接與後期處理）。

### 程式碼質量

**ruff**（lint + format）：
- 規則集：`E`/`F`/`I`/`UP`，忽略 `E402`（既有模式）和 `E501`（由 formatter 管理）
- line-length：120
- 排除 `.worktrees`、`.claude/worktrees` 目錄
- CI 中強制檢查：`ruff check . && ruff format --check .`

**pytest**：
- `asyncio_mode = "auto"`（無需手動標記 async 測試）
- 測試覆蓋範圍：`lib/` 和 `server/`，CI 要求 ≥80%
- 共用 fixtures 在 `tests/conftest.py`，工廠在 `tests/factories.py`，fakes 在 `tests/fakes.py`
- test 依賴在 `[dependency-groups] dev` 中，`uv sync` 預設安裝，生產映象透過 `--no-dev` 排除
