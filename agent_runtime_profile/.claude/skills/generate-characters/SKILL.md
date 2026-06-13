---
name: generate-characters
description: 生成角色設計參考圖（三檢視）。當使用者說"生成角色圖"、"畫角色設計"、想為新角色建立參考圖、或有角色缺少 character_sheet 時使用。確保影片中角色形象一致。
---

# 生成角色設計圖

使用 Gemini 3 Pro Image API 建立角色設計圖，確保整個影片中的視覺一致性。

> Prompt 編寫原則詳見 `.claude/references/content-modes.md` 的"Prompt 語言"章節。

## 角色描述編寫指南

編寫角色 `description` 時使用**敘事式寫法**，不要羅列關鍵詞。

**推薦**：
> "二十出頭的女子，身材纖細，鵝蛋臉上有一雙清澈的杏眼，柳葉眉微蹙時帶著幾分憂鬱。身著淡青色繡花羅裙，腰間繫著同色絲帶，顯得端莊而不失靈動。"

**要點**：用連貫段落描述外貌、服裝、氣質，包含年齡、體態、面部特徵、服飾細節。

## 命令列用法

```bash
# 生成所有待處理的角色
python .claude/skills/generate-characters/scripts/generate_character.py --all

# 生成指定單個角色
python .claude/skills/generate-characters/scripts/generate_character.py --character "{角色名}"

# 生成指定多個角色
python .claude/skills/generate-characters/scripts/generate_character.py --characters "{角色1}" "{角色2}" "{角色3}"

# 列出待生成的角色
python .claude/skills/generate-characters/scripts/generate_character.py --list
```

## 工作流程

1. **載入專案資料** — 從 project.json 找出缺少 `character_sheet` 的角色
2. **生成角色設計** — 根據描述構建 prompt，呼叫指令碼生成
3. **稽核檢查點** — 展示每張設計圖，使用者可批准或要求生成
4. **更新 project.json** — 更新 `character_sheet` 路徑

## Prompt 模板

```
一張專業的角色設計參考圖，{專案 style}。

角色「[角色名稱]」的三檢視設計稿。[角色描述 - 敘事式段落]

三個等比例全身像水平排列在純淨淺灰背景上：左側正面、中間四分之三側面、右側純側面輪廓。柔和均勻的攝影棚照明，無強烈陰影。
```

> 畫風由專案的 `style` 欄位決定，不使用固定的"漫畫/動漫"描述。
