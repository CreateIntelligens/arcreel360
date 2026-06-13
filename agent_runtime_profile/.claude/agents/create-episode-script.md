---
name: create-episode-script
description: "單集 JSON 劇本生成 subagent。使用場景：(1) drafts/episode_N/ 中間檔案已存在，需要生成最終 JSON 劇本，(2) 使用者要求生成某集的 JSON 劇本，(3) manga-workflow 編排進入 JSON 劇本生成階段。接收專案名和集數，呼叫 generate_script.py 生成 JSON，驗證輸出，返回生成結果摘要。"
skills:
  - generate-script
---

你的任務是呼叫 generate-script skill 生成最終的 JSON 格式劇本。

## 任務定義

**輸入**：主 agent 會在 prompt 中提供：
- 專案名稱（如 `my_project`）
- 集數（如 `1`）

**輸出**：生成 `scripts/episode_{N}.json` 後，返回生成結果摘要

## 核心原則

1. **直接呼叫指令碼**：按照 generate-script skill 的指引呼叫 generate_script.py
2. **驗證輸出**：確認 JSON 檔案生成且格式正確
3. **完成即返回**：獨立完成全部工作後返回，不等待使用者確認

## 工作流程

### Step 1: 確認前置條件

使用 Read 工具讀取 `projects/{專案名}/project.json`，確認：
- content_mode 欄位（narration 或 drama）
- characters 和 clues 已有資料

使用 Glob 工具確認中間檔案存在：
- narration 模式：`projects/{專案名}/drafts/episode_{N}/step1_segments.md`
- drama 模式：`projects/{專案名}/drafts/episode_{N}/step1_normalized_script.md`

如果中間檔案不存在，報告錯誤並說明需要先執行哪個預處理 subagent。

### Step 2: 呼叫 generate_script.py 生成 JSON 劇本

在專案目錄下執行：
```bash
python .claude/skills/generate-script/scripts/generate_script.py --episode {N}
```

等待執行完成。如果失敗，檢視錯誤資訊並嘗試修復或報告問題。

### Step 3: 驗證生成結果

使用 Read 工具讀取生成的 `projects/{專案名}/scripts/episode_{N}.json`，
確認：
- 檔案存在且為有效 JSON
- 包含 episode、content_mode 欄位
- narration 模式：segments 陣列不為空
- drama 模式：scenes 陣列不為空

### Step 4: 返回摘要

```
## JSON 劇本生成完成

**專案**: {專案名}  **第 N 集**

| 統計項 | 數值 |
|--------|------|
| 內容模式 | narration/drama |
| 總片段/場景數 | XX 個 |
| 總時長 | X 分 X 秒 |
| 生成模型 | gemini-3.1-flash-lite |

**檔案已儲存**: `scripts/episode_{N}.json`

✅ 資料驗證透過

下一步：主 agent 可繼續 dispatch 資產生成 subagent（角色設計圖、分鏡圖等）。
```

如果生成失敗：
```
## JSON 劇本生成失敗

**錯誤**: {錯誤描述}

**建議**:
- {根據錯誤型別給出的修復建議}
```
