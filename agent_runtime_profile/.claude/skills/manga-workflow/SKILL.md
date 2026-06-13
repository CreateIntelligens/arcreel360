---
name: manga-workflow
description: 將小說轉換為短影片的端到端工作流編排器。當使用者提到做影片、建立專案、繼續專案、檢視進度時必須使用此 skill。觸發場景包括但不限於："幫我把小說做成影片"、"開個新專案"、"繼續"、"下一步"、"看看專案進度"、"從頭開始"、"拆集"、"自動跑完流程"等。即使使用者只說了簡短的"繼續"或"下一步"，只要當前上下文涉及影片專案，就應該觸發。不要用於單個資產生成（如只重畫某張分鏡圖或只生成某個角色設計圖——那些有專門的 skill）。
---

# 影片工作流編排

你（主 agent）是編排中樞。你**不直接**處理小說原文或生成劇本，而是：
1. 檢測專案狀態 → 2. 決定下一階段 → 3. dispatch 合適的 subagent → 4. 展示結果 → 5. 獲取使用者確認 → 6. 迴圈

**核心約束**：
- 小說原文**永遠不載入到主 agent context**，由 subagent 自行讀取
- 每次 dispatch 只傳**檔案路徑和關鍵引數**，不傳大塊內容
- 每個 subagent 完成一個聚焦任務就返回，主 agent 負責階段間銜接
- 生成「世界觀／專案概述」時，必須寫入 `project.json.overview` 的結構化欄位（synopsis、genre、theme、world_setting）；純文字回覆不算完成

> 內容模式規格（畫面比例、時長等）詳見 `.claude/references/content-modes.md`。

---

## 階段 0：專案設定

### 新專案

1. 詢問專案名稱
2. 建立 `projects/{名稱}/` 及子目錄（source/、scripts/、characters/、clues/、storyboards/、videos/、drafts/、output/）
3. 建立 `project.json` 初始檔案
4. **詢問內容模式**：`narration`（預設）或 `drama`
5. 請使用者將小說文字放入 `source/`
6. **上傳後自動生成專案概述**（synopsis、genre、theme、world_setting）

### 概述／世界觀生成

**觸發**：`project.json.overview` 缺失、為空，或不是結構化物件。

- `gemini-full` / `openai-full`：呼叫 `generate_overview` 從 `source/` 生成並儲存；若已在對話中整理好內容，呼叫 `update_overview` 保存。
- Claude legacy：直接更新 `project.json.overview`，必須寫入物件而不是字串。
- 完成後重新檢查狀態；只有 `project.json.overview` 實際存在時，專案卡片進度才會從「專案概述」推進。

### 現有專案

1. 列出 `projects/` 中的專案
2. 顯示專案狀態摘要
3. 從上次未完成的階段繼續

---

## 狀態檢測

進入工作流後，使用 Read 讀取 `project.json`，使用 Glob 檢查檔案系統。按順序檢查，遇到第一個缺失項即確定當前階段：

0. overview 缺失、為空或非結構化？ → **階段 0**
1. characters/clues 為空？ → **階段 1**
2. 目標集 source/episode_{N}.txt 不存在？ → **階段 2**
3. 目標集 drafts/ 中間檔案不存在？ → **階段 3**
   - narration: `drafts/episode_{N}/step1_segments.md`
   - drama: `drafts/episode_{N}/step1_normalized_script.md`
4. scripts/episode_{N}.json 不存在？ → **階段 4**
5. 有角色缺少 character_sheet？ → **階段 5**（與階段 6 可並行）
6. 有 importance=major 線索缺少 clue_sheet？ → **階段 6**（與階段 5 可並行）
7. 有場景缺少分鏡圖？ → **階段 7**
8. 有場景缺少影片？ → **階段 8**
9. 全部完成 → 工作流結束，引導使用者在 Web 端匯出剪映草稿

**確定目標集數**：如果使用者未指定，找到最新的未完成集，或詢問使用者。

---

## 階段間確認協議

**每個 subagent 返回後**，主 agent 執行：

1. **展示摘要**：將 subagent 返回的摘要展示給使用者
2. **獲取確認**：使用 AskUserQuestion 提供選項：
   - **繼續下一階段**（推薦）
   - **重做此階段**（附加修改要求後重新 dispatch）
   - **跳過此階段**
3. **根據使用者選擇行動**

---

## 階段 1：全域性世界觀設計

**觸發**：project.json 中 characters 或 clues 為空

**dispatch `analyze-characters-clues` subagent**：

```
專案名稱：{project_name}
專案路徑：projects/{project_name}/
分析範圍：{整部小說 / 使用者指定的範圍}
已有角色：{已有角色名列表，或"無"}
已有道具：{已有道具名列表，或"無"}
已有場景：{已有場景名列表，或"無"}

請分析小說原文，提取角色、道具和重要場景資訊，寫入 project.json，返回摘要。
```

---

## 階段 2：分集規劃

**觸發**：目標集的 `source/episode_{N}.txt` 不存在

每次只切分當前需要製作的那一集。**主 agent 直接執行**（不 dispatch subagent）：

1. 確定原始檔：`source/_remaining.txt` 存在則使用，否則用原始小說檔案
2. 詢問使用者目標字數（如 1000 字/集）
3. 呼叫 `peek_split_point.py` 展示切分點附近上下文：
   ```bash
   python .claude/skills/manage-project/scripts/peek_split_point.py --source {原始檔} --target {目標字數}
   ```
4. 分析 nearby_breakpoints，建議自然斷點
5. 使用者確認後，先 dry run 驗證：
   ```bash
   python .claude/skills/manage-project/scripts/split_episode.py --source {原始檔} --episode {N} --target {目標字數} --anchor "{錨點文字}" --dry-run
   ```
6. 確認無誤後實際執行（去掉 `--dry-run`）

---

## 階段 3：單集預處理

**觸發**：目標集的 drafts/ 中間檔案不存在

根據 content_mode 選擇 subagent：

- **narration** → dispatch `split-narration-segments`
- **drama** → dispatch `normalize-drama-script`

dispatch prompt 包含：專案名稱、專案路徑、集數、本集小說檔案路徑、角色/道具/場景名稱列表。

---

## 階段 4：JSON 劇本生成

**觸發**：scripts/episode_{N}.json 不存在

**dispatch `create-episode-script` subagent**：傳入專案名稱、專案路徑、集數。

---

## 階段 5+6：角色設計 + 線索設計（可並行）

兩個任務互不依賴，**同時 dispatch 兩個 `generate-assets` subagent**（如果兩者都需要）。

### subagent A — 角色設計

**觸發**：有角色缺少 character_sheet

```
dispatch `generate-assets` subagent：
  任務型別：characters
  專案名稱：{project_name}
  專案路徑：projects/{project_name}/
  待生成項：{缺失角色名列表}
  指令碼命令：
    python .claude/skills/generate-characters/scripts/generate_character.py --all
  驗證方式：重新讀取 project.json，檢查對應角色的 character_sheet 欄位
```

### subagent B — 線索設計

**觸發**：有 importance=major 線索缺少 clue_sheet

```
dispatch `generate-assets` subagent：
  任務型別：clues
  專案名稱：{project_name}
  專案路徑：projects/{project_name}/
  待生成項：{缺失線索名列表}
  指令碼命令：
    python .claude/skills/generate-clues/scripts/generate_clue.py --all
  驗證方式：重新讀取 project.json，檢查對應線索的 clue_sheet 欄位
```

如果只有其中一個需要執行，只 dispatch 對應的一個。
兩個 subagent 全部返回後，合併摘要展示給使用者，進入階段間確認。

---

## 階段 7：分鏡圖生成

**觸發**：有場景缺少分鏡圖

**dispatch `generate-assets` subagent**：

```
dispatch `generate-assets` subagent：
  任務型別：storyboard
  專案名稱：{project_name}
  專案路徑：projects/{project_name}/
  指令碼命令：
    python .claude/skills/generate-storyboard/scripts/generate_storyboard.py episode_{N}.json
  驗證方式：重新讀取 scripts/episode_{N}.json，檢查各場景的 storyboard_image 欄位
```

---

## 階段 8：影片生成

**觸發**：有場景缺少影片

**dispatch `generate-assets` subagent**：

```
dispatch `generate-assets` subagent：
  任務型別：video
  專案名稱：{project_name}
  專案路徑：projects/{project_name}/
  指令碼命令：
    python .claude/skills/generate-video/scripts/generate_video.py episode_{N}.json --episode {N}
  驗證方式：重新讀取 scripts/episode_{N}.json，檢查各場景的 video_clip 欄位
```

---

## 靈活入口

工作流**不強制從頭開始**。根據狀態檢測結果，自動從正確的階段開始：

- "分析小說角色" → 只執行階段 1
- "建立第2集劇本" → 從階段 2 開始（如果角色已有）
- "繼續" → 狀態檢測找到第一個缺失項
- 指定具體階段（如"生成分鏡圖"）→ 直接跳到該階段

---

## 資料分層

- 角色/道具/場景完整定義**只存 project.json**，劇本中僅引用名稱
- 統計欄位（scenes_count、status、progress）**讀時計算**，不儲存
- 劇集後設資料在劇本儲存時**寫時同步**
