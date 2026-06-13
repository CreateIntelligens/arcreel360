---
name: generate-script
description: 使用 Gemini API 生成 JSON 劇本。由 create-episode-script subagent 呼叫。讀取 step1 中間檔案和 project.json，呼叫 Gemini 生成符合 Pydantic 模型的 JSON 劇本。
user-invocable: false
---

# generate-script

使用 Gemini API 生成 JSON 劇本。此 skill 由 `create-episode-script` subagent 呼叫，不直接面向使用者。

## 前置條件

1. 專案目錄下存在 `project.json`（包含 style、overview、characters、clues）
2. 已完成 Step 1 預處理：
   - narration：`drafts/episode_N/step1_segments.md`
   - drama：`drafts/episode_N/step1_normalized_script.md`

## 用法

### Step 1: 預處理（拆段 / 規範化）
```bash
# 執行說書模式拆段
python .claude/skills/generate-script/scripts/split_narration_segments.py --episode {N} [--source {path}] [--model {provider/model}] [--dry-run]

# 執行戲劇模式規範化
python .claude/skills/generate-script/scripts/normalize_drama_script.py --episode {N} [--source {path}] [--model {provider/model}] [--dry-run]
```
> `--source {path}` 可選。指定時直接使用該檔；未指定時會先找 `source/episode_{N}.txt`。若仍不存在，narration 會串接 `source/` 目錄下的原文並按 `project.json` 集數均分；drama 目前會串接並使用整本原文。`--model {provider/model}` 可選；未指定時使用專案或全域劇本模型。

### Step 2: 生成劇本
```bash
# 生成指定劇集的劇本
python .claude/skills/generate-script/scripts/generate_script.py --episode {N}

# 自定義輸出路徑
python .claude/skills/generate-script/scripts/generate_script.py --episode {N} --output scripts/ep1.json

# 預覽 Prompt（不實際呼叫 API）
python .claude/skills/generate-script/scripts/generate_script.py --episode {N} --dry-run
```

## 生成流程

指令碼內部透過 `ScriptGenerator` 完成以下步驟：

1. **載入 project.json** — 讀取 content_mode、characters、clues、overview、style
2. **載入 Step 1 中間檔案** — 根據 content_mode 選擇 `step1_segments.md`（narration）或 `step1_normalized_script.md`（drama）
3. **構建 Prompt** — 將專案概述、風格、角色、線索和中間檔案內容組合成完整 prompt
4. **呼叫 Gemini API** — 使用 `gemini-3.1-flash-lite` 模型，傳入 Pydantic schema 作為 `response_schema` 約束輸出格式
5. **Pydantic 驗證** — 用 `NarrationEpisodeScript`（narration）或 `DramaEpisodeScript`（drama）校驗返回 JSON
6. **補充後設資料** — 寫入 episode、content_mode、統計資訊（片段/場景數、總時長）、時間戳

## 輸出格式

生成的 JSON 檔案儲存至 `scripts/episode_N.json`，核心結構：

- `episode`、`content_mode`、`novel`（title、chapter、source_file）
- narration 模式：`segments` 陣列（每個片段包含 visual、novel_text、duration_seconds 等）
- drama 模式：`scenes` 陣列（每個場景包含 visual、dialogue、action、duration_seconds 等）
- `metadata`：total_segments/total_scenes、created_at、generator
- `duration_seconds`：全集總時長（秒）

## `--dry-run` 輸出

列印將傳送給 Gemini 的完整 prompt 文字，不呼叫 API、不寫檔案。用於檢查 prompt 質量和長度。

> 支援的兩種模式規格詳見 `.claude/references/content-modes.md`。
