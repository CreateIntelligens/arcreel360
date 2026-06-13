---
name: generate-clues
description: 生成道具線索設計參考圖。當使用者說"生成線索圖"、"畫道具設計"、想為重要物品建立參考圖、或有 major 線索缺少 clue_sheet 時使用。確保跨場景視覺一致。
---

# 生成線索設計圖

使用 Gemini 3 Pro Image API 建立道具線索設計圖，確保整個影片中重要物品的視覺一致性。

> Prompt 編寫原則詳見 `.claude/references/content-modes.md` 的"Prompt 語言"章節。

## 線索描述編寫指南

編寫 `description` 時使用**敘事式寫法**，不要羅列關鍵詞。

**示例**：
> "一塊翠綠色的祖傳玉佩，約拇指大小，玉質溫潤透亮。表面雕刻著精緻的蓮花紋樣，花瓣層層舒展。玉佩上繫著一根紅色絲繩，打著傳統的中國結。"

**要點**：用連貫段落描述形態、質感、細節，突出能跨場景識別的獨特特徵。

## 命令列用法

```bash
# 生成所有待處理的線索
python .claude/skills/generate-clues/scripts/generate_clue.py --all

# 生成指定單個線索
python .claude/skills/generate-clues/scripts/generate_clue.py --clue "玉佩"

# 生成指定多個線索
python .claude/skills/generate-clues/scripts/generate_clue.py --clues "玉佩" "密信" "戒指"

# 列出待生成的線索
python .claude/skills/generate-clues/scripts/generate_clue.py --list
```

## 工作流程

1. **載入專案後設資料** — 從 project.json 找出 `importance='major'` 且缺少 `clue_sheet` 的線索
2. **生成線索設計** — 呼叫指令碼生成道具參考圖
3. **稽核檢查點** — 展示每張設計圖，使用者可批准或要求生成
4. **更新 project.json** — 更新 `clue_sheet` 路徑

## Prompt 模板

```
一張專業的道具設計參考圖，{專案 style}。

道具「[名稱]」的多視角展示。[詳細描述 - 敘事式段落]

三個檢視水平排列在純淨淺灰背景上：左側正面全檢視、中間45度側檢視展示立體感、右側關鍵細節特寫。柔和均勻的攝影棚照明，高畫質質感，色彩準確。
```

## 質量檢查

- 三個視角清晰一致、細節符合描述、特殊紋理清晰可見
