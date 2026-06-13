# 設計：補齊非 Claude provider 工作流（分集切分能力對齊 + 前端入口）

- 狀態：Draft
- 日期：2026-05-12

## 背景與問題

ArcReel 的 agent runtime 支援三個 full-tier provider：`claude`（Claude Agent SDK）、`gemini-full`（Google ADK）、`openai-full`（OpenAI Agents SDK）。三者**能力應該對等**，但目前並非如此：

- **Claude** 透過 `.claude/agents/*.md` 定義的「真 subagent」（`analyze-characters-clues`、`split-narration-segments`、`normalize-drama-script`、`create-episode-script`、`generate-assets`）+ Bash 工具呼叫 `manage-project/scripts/*.py`，能跑完整的 8 階段工作流。
- **gemini-full / openai-full** 只有 `skill_function_declarations.py` 裡的 7 個 function（`generate_script`、`generate_characters`、`generate_clues`、`manga_workflow_status`、`generate_storyboard`、`generate_video`、`compose_video`）+ 一個「假的」`run_subagent`（同步呼叫上述 handler）。**缺「分集切分（peek + split）」與「拆段/規範化（preprocess）」這兩步**，導致它們無法從零把小說推進到劇本。

額外缺口：**分集切分（episode 的源頭）目前只能由 agent 觸發**，前端完全沒有入口。使用者上傳小說後若不跟 agent 對話，會卡在「沒有 episode → 工作區沒有劇集 tab → 看不到生成劇本/分鏡/影片的按鈕」。

確定性腳本（`peek_split_point.py` / `split_episode.py` / `split_narration_segments.py` / `normalize_drama_script.py` / `_text_utils.py`）**全部已存在**，缺的只是「把邏輯收斂到 provider-agnostic 的位置」+「在 gemini/openai 與 HTTP 層暴露」。

## 目標

1. **能力對齊**：gemini-full / openai-full 取得 `peek_split_point`、`split_episode`、`preprocess_episode` 三個 function，能跑完整工作流。Claude 仍可用其 subagent 機制 —— 那是實作細節，不代表 Claude 更高級；能力上三家平等。
2. **前端入口**：新增 `POST .../episodes/peek` 與 `POST .../episodes/split` 兩個 HTTP API + 前端「分集切分」面板，讓不使用 agent 的人也能從小說切出劇集。
3. **單一真相源**：分集切分的核心邏輯收斂到 `lib/`，Claude CLI 腳本 / gemini-openai function / HTTP API 三條路徑共用同一份。

## 非目標

- 不做「統一 function registry」的大重構，不動 Claude 的 `.claude/agents/`。
- 不為「角色/線索提取」新增 function（提取的推理本來就由 agent 做，寫入走既有 `generate_characters` / `generate_clues`）。
- 不做「手動新增單一 episode」的入口（只做 peek+split）。
- 不全面拆分 `ProjectManager`（只做與本任務相關的最小拆分，且視耦合度可退回不拆）。

## 架構

```
                    ┌─────────────────────────────────────┐
                    │  lib/episode_splitter.py (純函式)    │
                    │  count_chars / find_char_offset /    │
                    │  find_natural_breakpoints /          │
                    │  peek_split / split_episode_text     │
                    └──────────────┬──────────────────────┘
                                   │ (純文字運算，無 I/O、無 cwd 假設)
       ┌───────────────────────────┼───────────────────────────┐
       │                           │                           │
┌──────▼───────┐         ┌─────────▼──────────┐       ┌─────────▼─────────────┐
│ Claude CLI    │         │ gemini/openai      │       │ HTTP API              │
│ 腳本(wrapper) │         │ function handlers  │       │ projects.py 路由      │
│ peek_split_   │         │ skill_function_    │       │ POST .../episodes/    │
│ point.py 等   │         │ declarations.py    │       │   peek, split         │
└───────────────┘         └─────────┬──────────┘       └─────────┬─────────────┘
                                    │                            │
                                    └────────────┬───────────────┘
                                                 │ (落地：寫檔 + 更新 project.json)
                                       ┌─────────▼──────────────────┐
                                       │ ProjectManager.            │
                                       │   commit_episode_split()   │
                                       └────────────────────────────┘
```

`preprocess` 走類似結構：`lib/episode_preprocess.py`（純函式 `run_preprocess(project_path, episode) -> dict`）← 既有 router `_run_preprocess_for_content_mode` 抽出來；router 與 `_handle_preprocess_episode` 都 import 它。

## 元件設計

### 1. `lib/episode_splitter.py`（新增，共享核心）

把 `agent_runtime_profile/.claude/skills/manage-project/scripts/_text_utils.py` + `peek_split_point.py` + `split_episode.py` 的核心邏輯抽進來。純函式、無 argparse、無 cwd 假設、不 print（拋例外或回 dict）。**不含寫檔/更新 project.json**（那放 ProjectManager）。

```python
# --- 文字工具（自 _text_utils.py 搬來）---
def count_chars(text: str) -> int                          # 非空行字元數（既有規則）
def find_char_offset(text: str, target_count: int) -> int  # 第 N 個有效字元 → 原文 offset
def find_natural_breakpoints(text, center_offset, window=200) -> list[dict]

# --- peek：預覽切分點（read-only）---
def peek_split(source_text: str, target_chars: int, context: int = 200) -> dict
# 回 {total_chars, target_chars, target_offset, before_context, after_context, breakpoints: [...]}
# target_chars >= total_chars → raise ValueError

# --- split：算精確切點與兩半文字 ---
def split_episode_text(source_text: str, target_chars: int, anchor: str, context: int = 500) -> dict
# 回 {split_pos, part_before, part_after, before_preview, after_preview}
# anchor 找不到 / 多個 → raise ValueError（訊息附候選列表）
```

### 2. `lib/episode_preprocess.py`（新增）

把 `server/routers/projects.py` 的 `_run_preprocess_for_content_mode` 核心搬出來：

```python
def run_preprocess(project_path: Path, episode: int) -> dict
# 依 project.json 的 content_mode 分流：
#   narration → 呼叫 split_narration_segments 邏輯
#   drama     → 呼叫 normalize_drama_script 邏輯
# 回 {step1_path, content_mode, ...}（沿用既有回傳）
```

`split_narration_segments.py` / `normalize_drama_script.py` 的核心是否也抽進 lib，由實作階段視耦合度決定（過渡期可用 subprocess，但目標是 import）。

### 3. `lib/project_episodes.py`（新增，可選）

`project_manager.py` 已 1500+ 行（超過 coding-style 的 800 行上限）。趁這次把「劇集/劇本相關」方法（`add_episode`、`sync_episode_from_script`、`save_script`、`load_script`、新的 `commit_episode_split`）抽到此模組（mixin 或自由函式），`ProjectManager` 對外暴露同名方法（轉呼叫），呼叫端零改動。

**逃生口**：若實作時評估這個拆分牽動過多測試，退回到「只在 `project_manager.py` 加 `commit_episode_split` 不拆」，並在本文件補記「project_manager.py 過長」為已知債務。兩種都允許。

`commit_episode_split` 的契約：

```python
def commit_episode_split(self, project_name: str, source_rel: str, episode: int,
                         part_before: str, part_after: str, title: str | None = None) -> dict
# 寫 source/episode_{episode}.txt（= part_before）
# 寫 source/_remaining.txt（= part_after）—— 下一集的新起點
# 不修改原始 source 檔
# 在 project.json 的 episodes 加 {episode, title?, ...}（已存在則更新）
# 回更新後的 project dict
```

### 4. `server/agent_runtime/skill_function_declarations.py`（修改，+3 function）

`adk_tool_adapters.py` 與 `openai_tool_adapters.py` 自動從 `SKILL_DECLARATIONS` / `SKILL_HANDLERS` 建工具 → 加完 gemini 與 openai 自動跟上，**不改 adapter**。

| function | 用途 | 參數 | 回傳（成功） |
|---|---|---|---|
| `peek_split_point` | 預覽分集切分點（read-only） | `source` (source/ 下相對路徑), `target_chars` (int), `context` (int, 預設 200) | `{total_chars, target_chars, target_offset, before_context, after_context, breakpoints}` |
| `split_episode` | 執行分集切分 | `source`, `episode` (int), `target_chars` (int), `anchor` (str, 切點前 10~20 字), `context` (int, 預設 500) | `{episode, episode_file, remaining_file, part_before_chars, part_after_chars, split_pos}` |
| `preprocess_episode` | 拆段/規範化 → 產 step1 中介檔 | `episode` (int) | `{step1_path, content_mode, ...}` |

handler 實作：
- `_handle_peek_split_point` → 解析 `ctx.project_manager.get_project_path() / source`（驗證在 `source/` 下、檔案存在）→ `episode_splitter.peek_split(...)` → 回 dict。任何失敗 → 回 `{"ok": False, "error": ..., "reason": ...}`。
- `_handle_split_episode` → `episode_splitter.split_episode_text(...)` 算切點 → `pm.commit_episode_split(...)` 落地 → **寫入後驗證**：`pm.load_project()` 確認新 episode 進了 `episodes`，沒進 → 回 `ok: False`。anchor 找不到/多個 → 回 `ok: False` + 候選列表。
- `_handle_preprocess_episode` → `episode_preprocess.run_preprocess(...)`。

**角色/線索提取引導**（不加 function）：在 `agent_runtime_profile/CLAUDE.md`（三 provider 共用的系統 prompt）加一段：「執行角色/線索提取時：先用 fs_read 讀 `source/` 的小說原文 → 自行分析出 characters/clues → 呼叫 `generate_characters` / `generate_clues` 寫入 → 檢查回傳 `ok` 是否為 true，false 代表未成功，不可回報完成。」

### 5. `server/routers/projects.py`（修改，+2 路由）

| 路由 | body | 回傳 | 核心 |
|---|---|---|---|
| `POST /projects/{name}/episodes/peek` | `{source, target_chars, context?}` | 同 `peek_split_point` function | `episode_splitter.peek_split(...)` |
| `POST /projects/{name}/episodes/split` | `{source, episode, target_chars, anchor, context?}` | 同 `split_episode` function | `episode_splitter.split_episode_text(...)` + `pm.commit_episode_split(...)` |

沿用既有模式：`asyncio.to_thread(_sync)`、`project_change_source("webui")`、`get_project_manager()`、錯誤轉 `HTTPException`（404 專案不存在 / 400 anchor 找不到（附候選）/ 422 參數錯）。`source` 路徑安全：router 層驗證必須在 `source/` 下（複用 `_safe_subpath` / `is_relative_to`）。

同時把 `_run_preprocess_for_content_mode` 抽到 `lib/episode_preprocess.py`，既有 `POST .../episodes/{episode}/preprocess` 改為呼叫它（行為不變）。

### 6. 既有 CLI 腳本改 wrapper（修改）

- `agent_runtime_profile/.claude/skills/manage-project/scripts/_text_utils.py` → `from lib.episode_splitter import count_chars, find_char_offset, find_natural_breakpoints`（re-export，import 路徑不變）。
- `peek_split_point.py` / `split_episode.py` → argparse 解析後呼叫 `lib.episode_splitter` + ProjectManager 落地方法，**stdout 輸出格式逐字不變**（Claude provider 依賴）。
- `split_narration_segments.py` / `normalize_drama_script.py` → 視 §2 決定，可能改 wrapper 或不動。

### 7. 前端

- `frontend/src/api.ts`：`API.peekEpisodeSplit(name, body)` / `API.splitEpisode(name, body)`。
- `frontend/src/components/canvas/timeline/EpisodeSplitPanel.tsx`（新元件，與 `EpisodeActionsBar` 同層）：
  - 顯示時機：專案工作區裡 `episodes` 為空、且 `source/` 有檔案時（在 `TimelineCanvas` 判斷後掛載）。
  - 流程：選 `source/` 檔 + 填目標字數（預設 3000）→「預覽切點」（peek API）→ 顯示總字數 + 前後文（高亮建議切點）+ 候選自然斷點列表 → 使用者選一個斷點（或微調 anchor）→「執行切分」（split API）→ 成功後 toast + 觸發專案重新載入（episodes 多一筆 → 工作區出現第 1 集 tab + `EpisodeActionsBar`）。
  - 切分後 `source/_remaining.txt` 是新起點，panel 可繼續切下一集（target 從 1 重新算）。
- `frontend/src/components/canvas/timeline/TimelineCanvas.tsx`：掛載 `EpisodeSplitPanel`。

## 資料流（典型：使用者從前端切出第 1 集）

1. 使用者上傳 `source/novel.txt`（既有 `POST /files/upload?upload_type=source`）。
2. 工作區偵測 `episodes == []` 且 `source/` 非空 → 顯示 `EpisodeSplitPanel`。
3. 使用者填 target=3000 → 按「預覽切點」→ `POST .../episodes/peek {source:"source/novel.txt", target_chars:3000}` → 後端 `episode_splitter.peek_split(text, 3000)` → 回前後文 + 候選斷點。
4. 使用者選候選斷點（其 `text` 當作 anchor）→ 按「執行切分」→ `POST .../episodes/split {source, episode:1, target_chars:3000, anchor:"...選的文字..."}` → 後端：`episode_splitter.split_episode_text(...)` 算切點 → `pm.commit_episode_split("proj", "source/novel.txt", 1, part_before, part_after)` 寫 `source/episode_1.txt` + `source/_remaining.txt` + project.json episodes += `{episode:1}` → 寫入後驗證 → 回 `{episode:1, episode_file:"source/episode_1.txt", ...}`。
5. 前端收到成功 → toast + 重新載入專案 → 工作區出現第 1 集 tab、`EpisodeActionsBar`（可按「重新拆段」「生成劇本」…）。
6. agent 路徑同理：gemini/openai agent 呼叫 `peek_split_point` → `split_episode` function，走同一套 lib 邏輯。

## 錯誤處理

- function handler 失敗一律回 `{"ok": False, "error": <code>, "reason": <人話>}`（沿用本 session 已建立的 fail-loud 慣例）；寫入操作後做「寫入後驗證」（確認 episode 真的進了 project.json，沒進就回 `ok: False`）。
- HTTP 層：404（專案不存在）、400（anchor 找不到，回應 body 附候選斷點供前端提示）、422（參數錯，如 target ≥ 總字數、source 越界）。
- `episode_splitter` 純函式以 `ValueError` 表達錯誤（target 超界、anchor 找不到/多個），由上層轉成各自的錯誤格式。
- `source` 路徑遍歷防護：lib 不假設 cwd，由呼叫方（handler / router）負責把相對路徑解析到專案目錄並驗證在 `source/` 下。

## 測試策略

新增：
- `tests/test_episode_splitter.py` — `lib/episode_splitter.py` 純 unit test（無 I/O）：count_chars 規則、find_char_offset、find_natural_breakpoints、peek_split（含 target 超界 ValueError）、split_episode_text（含 anchor 找不到/多個 ValueError）。
- `tests/test_episode_split_routes.py` — `POST .../episodes/peek` 與 `.../split` 整合測試（tmp project fixture）：成功路徑、404、400（anchor 找不到）、422（參數錯）、寫入後 project.json 正確。
- `tests/test_episode_split_skill.py` — `_handle_peek_split_point` / `_handle_split_episode` / `_handle_preprocess_episode` 測試：成功回傳形狀、失敗回 `ok: False`、寫入後驗證攔截。
- `frontend/src/components/canvas/timeline/EpisodeSplitPanel.test.tsx` — 渲染、peek 呼叫、選斷點、split 呼叫、成功後回呼。Mock `API.peekEpisodeSplit` / `API.splitEpisode`。
- 既有 `tests/test_project_events_service.py` 等若因 ProjectManager 拆分受影響，須一併更新（拆分採「對外同名方法轉呼叫」即可最小化衝擊）。

驗收：
- `uv run ruff check . && uv run ruff format --check .` 全綠。
- `uv run python -m pytest` 全綠（CI 要求覆蓋率 ≥80%，新 lib 模組要測到位）。
- 前端 `pnpm test` + typecheck 全綠（用 Node 22 / pnpm 11.1.0：`export PATH="$HOME/.nvm/versions/node/v22.21.1/bin:$PATH"` + `CI=true COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack pnpm@11.1.0 ...`）。
- Claude provider 路徑回歸：`peek_split_point.py` / `split_episode.py` 的 stdout 輸出與改 wrapper 前逐字一致。

## 完整檔案清單

新增：
- `lib/episode_splitter.py`
- `lib/episode_preprocess.py`
- `lib/project_episodes.py`（若決定拆 ProjectManager）
- `frontend/src/components/canvas/timeline/EpisodeSplitPanel.tsx`
- `frontend/src/components/canvas/timeline/EpisodeSplitPanel.test.tsx`
- `tests/test_episode_splitter.py`
- `tests/test_episode_split_routes.py`
- `tests/test_episode_split_skill.py`

修改：
- `server/agent_runtime/skill_function_declarations.py`（+3 handler/decl）
- `server/routers/projects.py`（+2 路由，抽 `_run_preprocess_for_content_mode` 到 lib）
- `lib/project_manager.py`（+`commit_episode_split`，可能拆分到 `lib/project_episodes.py`）
- `agent_runtime_profile/.claude/skills/manage-project/scripts/_text_utils.py`（→ re-export from lib）
- `agent_runtime_profile/.claude/skills/manage-project/scripts/peek_split_point.py`（→ wrapper）
- `agent_runtime_profile/.claude/skills/manage-project/scripts/split_episode.py`（→ wrapper）
- `agent_runtime_profile/.claude/skills/manage-project/scripts/split_narration_segments.py` / `normalize_drama_script.py`（視 §2 決定）
- `agent_runtime_profile/.claude/skills/manage-project/SKILL.md`（同步說明）
- `agent_runtime_profile/CLAUDE.md`（角色提取引導文字）
- `frontend/src/api.ts`（+2 method）
- `frontend/src/components/canvas/timeline/TimelineCanvas.tsx`（掛載 EpisodeSplitPanel）

## 實作備註

- 實作交由 codex subagent 執行（多檔案、機械性改動為主）。
- 改動量大，建議分階段提交：(1) `lib/episode_splitter.py` + 測試 + CLI 腳本改 wrapper（Claude 路徑回歸驗證）；(2) function handlers + 測試；(3) HTTP API + 前端 + 測試；(4) `lib/episode_preprocess.py` 抽取 + `preprocess_episode` function。
