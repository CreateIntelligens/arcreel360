# AI 影片生成工作空間

---

## 重要總則

以下規則適用於整個專案的所有操作：

### 語言規範
- **回答使用者必須使用繁體中文**：所有回覆、思考過程、任務清單及計劃檔案，均須使用繁體中文；除非使用者明確要求翻譯或輸出其他語言，否則不要使用簡體中文或英文作為主要回覆語言
- **影片內容必須為繁體中文**：所有生成的影片對話、旁白、字幕均使用繁體中文
- **文件使用中文**：所有的 Markdown 檔案均使用中文編寫
- **Prompt 使用中文**：圖片生成/影片生成使用的 prompt 應使用中文編寫

### 影片規格
- **影片比例**：由專案 `aspect_ratio` 配置決定，無需在 prompt 中指定
  - 說書+畫面模式預設：**9:16 豎屏**
  - 劇集動畫模式預設：16:9 橫屏
- **單片段/場景時長**：由影片模型能力和專案 `default_duration` 配置決定
  - 說書+畫面模式預設：**4 秒**
  - 劇集動畫模式預設：8 秒
- **圖片解析度**：1K
- **影片解析度**：1080p
- **生成方式**：每個片段/場景獨立生成，使用分鏡圖作為起始幀

> **關於 extend 功能**：Veo 3.1 extend 功能僅用於延長單個片段/場景，
> 每次固定 +7 秒，不適合用於串聯不同鏡頭。不同片段/場景之間使用 ffmpeg 拼接。

### 音訊規範
- **BGM 自動禁止**：透過 `negative_prompt` API 引數自動排除背景音樂

### 指令碼呼叫
- **Skill 內部指令碼**：各 skill 的可執行指令碼位於 profile 目錄的 `skills/{skill-name}/scripts/` 下。
  你在執行時的 cwd 是專案目錄，該目錄下有一個指向 profile 的 symlink（名稱見 `lib/agent_profile.py` 的 `PROJECT_PROFILE_LINK_NAME`，目前為 `.claude`），
  因此可用相對路徑 `python .claude/skills/{skill-name}/scripts/{script}.py` 呼叫。
- **虛擬環境**：預設已啟用，指令碼無需手動啟用 .venv

---

## 內容模式

系統支援兩種內容模式（說書+畫面 / 劇集動畫），透過 `project.json` 的 `content_mode` 欄位切換。

> 詳細規格（畫面比例、時長、資料結構、預處理 Agent 等）見 profile 目錄的 `references/content-modes.md`（相對路徑：`.claude/references/content-modes.md`）。

---

## 專案結構

- `projects/{專案名}` - 影片專案的工作空間（執行時的 cwd）
- `lib/` - 共享 Python 庫（Gemini API 封裝、專案管理）
- profile 目錄的 `skills/` - 可用的 skills（從專案 cwd 透過 symlink 存取，相對路徑 `.claude/skills/`）

## 架構：編排 Skill + 聚焦 Subagent

```
主 Agent（編排層 — 極輕量）
  │  只持有：專案狀態摘要 + 使用者對話歷史
  │  職責：狀態檢測、流程決策、使用者確認、dispatch subagent
  │
  ├─ dispatch → analyze-characters-clues     全域性角色/線索提取
  ├─ dispatch → split-narration-segments     說書模式片段拆分
  ├─ dispatch → normalize-drama-script       劇集模式規範化劇本
  ├─ dispatch → create-episode-script        JSON 劇本生成（預載入 generate-script skill）
  └─ dispatch → generate-assets              資產生成（角色/線索/分鏡/影片）
```

### Skill/Agent 邊界原則

| 型別 | 用途 | 示例 |
|------|------|------|
| **Subagent（聚焦任務）** | 需要大量上下文或推理分析 → 保護主 agent context | analyze-characters-clues、split-narration-segments |
| **Skill（在 subagent 內呼叫）** | 確定性指令碼執行 → API 呼叫、檔案生成 | generate-script、generate-characters |
| **主 Agent 直接操作** | 僅限輕量操作 | 讀專案狀態、簡單檔案操作、使用者互動 |

### 關鍵約束

- **Subagent 不能 spawn subagent**：多步工作流只能透過主 agent 鏈式 dispatch
- **小說原文不進入主 agent**：由 subagent 自行讀取，主 agent 只傳檔案路徑
- **每個 subagent 一個聚焦任務**：完成即返回，不在內部做多步使用者確認

### 職責邊界

- **禁止編寫程式碼**：不得建立或修改任何程式碼檔案（.py/.js/.sh 等），資料處理必須透過現有 skill 指令碼完成
- **程式碼 bug 上報**：如果明確判斷 skill 指令碼出現的是程式碼 bug（而非引數或環境問題），向使用者報告錯誤並建議反饋給開發者

## 可用 Skills

| Skill | 觸發命令 | 功能 |
|-------|---------|------|
| manga-workflow | `/manga-workflow` | 編排 skill：狀態檢測 + subagent dispatch + 使用者確認 |
| manage-project | — | 專案管理工具集：分集切分（peek+split）、角色/線索批次寫入 |
| generate-script | — | 使用 Gemini 生成 JSON 劇本（由 subagent 呼叫） |
| generate-characters | `/generate-characters` | 生成角色設計圖 |
| generate-clues | `/generate-clues` | 生成線索設計圖 |
| generate-storyboard | `/generate-storyboard` | 生成分鏡圖片 |
| generate-video | `/generate-video` | 生成影片 |

## 快速開始

新使用者請使用 `/manga-workflow` 開始完整的影片創作流程。

## 工作流程概覽

`/manga-workflow` 編排 skill 按以下階段推進。**「等待使用者確認」只發生在「是否進入下一階段」這一個決策點**，
而**不是**對「資料是否寫入」再確認一次——寫入工具（`update_overview` / `generate_characters` 等）一旦回 `ok: true`，
資料就已實際存入 `project.json`，已成定局。此時正確的問法是「○○已完成並儲存，要繼續進入下一階段嗎？」，
**嚴禁**講出「是否確認存入」「是否將此版本存入專案」這類問句——那會讓使用者誤以為資料還沒存。

階段如下：

1. **專案設定**：建立專案、上傳小說、生成專案概述
2. **全域性角色/線索設計** → dispatch `analyze-characters-clues` subagent
3. **分集規劃** → 主 agent 直接執行 peek+split 切分（manage-project 工具集）
4. **單集預處理** → dispatch `split-narration-segments`（narration）或 `normalize-drama-script`（drama）
5. **JSON 劇本生成** → dispatch `create-episode-script` subagent
6. **角色設計 + 線索設計**（可並行） → dispatch `generate-assets` subagent
7. **分鏡圖生成** → dispatch `generate-assets` subagent
8. **影片生成** → dispatch `generate-assets` subagent

工作流支援**靈活入口**：狀態檢測自動定位到第一個未完成的階段，支援中斷後恢復。
影片生成完成後，使用者可在 Web 端匯出為剪映草稿。

## 關鍵原則

- **角色一致性**：每個場景都使用分鏡圖作為起始幀，確保角色形象一致
- **線索一致性**：重要物品和環境元素透過 `clues` 機制固化，確保跨場景一致
- **分鏡連貫性**：使用 segment_break 標記場景切換點，後期可新增轉場效果
- **質量控制**：每個場景生成後檢查質量，可單獨生成不滿意的場景

### 角色/線索提取

提取角色與線索時：
1. 先用 `fs_read` 讀 `source/` 下的小說原文；檔案較大時可分段讀取
2. 自行分析 `characters`（`name` / `description` / `voice_style`）與 `clues`（`name` / `clue_type` / `description` / `importance`）
3. 呼叫 `generate_characters` / `generate_clues` 寫入 `project.json`
4. 檢查回傳的 `ok` 欄位；`false` 代表未成功寫入，不可回報「已定義完畢」，必須依 `reason` 修正後重試

### 專案概述/世界觀

> 🔴 **鋼定規則 — 違反即視為任務失敗：**
>
> 1. **「生成世界觀」「寫入世界觀」「生成概述」一律是工具呼叫任務，不是寫作任務。** 收到這類請求，你**必須實際發出 `update_overview`（已有整理好的內容）或 `generate_overview`（從 source/ 自動生成）的 function call**。把世界觀內容打在回覆裡、列成 Markdown 給使用者看——**不算完成**，專案進度不會推進。
> 2. **嚴禁「假裝呼叫工具」。** 不可在回覆裡寫「正在呼叫 `update_overview`…」「已寫入 project.json」這類敘述句卻不實際發出 function call。要嘛真的呼叫，要嘛明說你還沒呼叫。
> 3. **未看到工具回傳的 `tool_result` / `ok: true` 之前，不可向使用者回報「已寫入」「已完成」「已記錄」。** 只有 function call 真正執行並回成功，才算數。
> 4. 若 `fs_write` 對 `project.json` 回 `error: "use_dedicated_tool"`，代表你選錯工具——立刻改用 `update_overview`，不要重試 `fs_write`。
> 5. **工具回 `ok: true` 後,世界觀就「已存入」,不可再問「是否確認存入」「是否將此版本存入專案」。** 這類問句邏輯矛盾——資料已成定局。若要徵詢使用者,只能問「世界觀已儲存,要繼續進入角色設定嗎?」這種「下一階段」問題。

世界觀必須儲存到 `project.json.overview`，格式必須是物件：

```json
{
  "synopsis": "...",
  "genre": "...",
  "theme": "...",
  "world_setting": "..."
}
```

`gemini-full` / `openai-full` 呼叫 `generate_overview` 或 `update_overview`；Claude legacy 可直接編輯 `project.json`。

**正確做法範例**：使用者說「幫我根據原文生成世界觀」→ 你 `fs_read` 讀 `source/` 原文 → 自行整理出 synopsis/genre/theme/world_setting 四個欄位 → **實際發出 `update_overview` function call 帶上這四個欄位** → 看到回傳 `ok: true` → 才回覆使用者「世界觀已寫入，專案進度已推進到『世界觀』階段」。

## 專案目錄結構

```
projects/{專案名}/
├── project.json       # 專案後設資料（角色、線索、劇集、風格）
├── source/            # 原始小說內容
├── scripts/           # 分鏡劇本 (JSON)
├── characters/        # 角色設計圖
├── clues/             # 線索設計圖
├── storyboards/       # 分鏡圖片
├── videos/            # 生成的影片
└── output/            # 最終輸出
```

### project.json 核心欄位

- `title`、`content_mode`（`narration`/`drama`）、`style`、`style_description`
- `overview`：專案概述（synopsis、genre、theme、world_setting）
- `episodes`：劇集核心後設資料（episode、title、script_file）
- `characters`：角色完整定義（description、character_sheet、voice_style）
- `clues`：線索完整定義（type、description、importance、clue_sheet）

### 資料分層原則

- 角色/線索的完整定義**只儲存在 project.json**，劇本中僅引用名稱
- `scenes_count`、`status`、`progress` 等統計欄位由 StatusCalculator **讀時計算**，不儲存
- 劇集後設資料（episode/title/script_file）在劇本儲存時**寫時同步**
