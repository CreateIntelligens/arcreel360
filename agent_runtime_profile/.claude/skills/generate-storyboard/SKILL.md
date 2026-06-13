---
name: generate-storyboard
description: 為劇本場景生成分鏡圖。當使用者說"生成分鏡"、"預覽場景畫面"、想生成某些分鏡圖、或劇本中有場景缺少分鏡圖時使用。自動保持角色和畫面連續性。
---

# 生成分鏡圖

透過生成佇列建立分鏡圖，畫面比例根據 content_mode 自動設定。

> 內容模式規格詳見 `.claude/references/content-modes.md`。

## 命令列用法

```bash
# 提交所有缺失分鏡圖到生成佇列（自動檢測 content_mode）
python .claude/skills/generate-storyboard/scripts/generate_storyboard.py script.json

# 為單個場景生成
python .claude/skills/generate-storyboard/scripts/generate_storyboard.py script.json --scene E1S05

# 為多個場景生成
python .claude/skills/generate-storyboard/scripts/generate_storyboard.py script.json --scene-ids E1S01 E1S02
```

> `--scene-ids` 和 `--segment-ids` 是同義別名（後者為 narration 模式的習慣稱呼），效果相同。以下統一使用 `--scene-ids`。

> **選擇規則**：`--scene` 重生成一個；`--scene-ids` 重生成多個；未提供則提交所有缺失項。

> **注意**：指令碼要求 generation worker 線上，worker 負責實際影象生成與速率控制。

## 工作流程

1. **載入專案和劇本** — 確認所有角色都有 `character_sheet` 影象
2. **生成分鏡圖** — 指令碼自動檢測 content_mode，按相鄰關係串聯依賴任務
3. **稽核檢查點** — 展示每張分鏡圖，使用者可批准或要求生成
4. **更新劇本** — 更新 `storyboard_image` 路徑和場景狀態

## 角色一致性機制

指令碼自動處理以下參考圖傳入，無需手動指定：
- **character_sheet**：場景中出場角色的設計圖，保持外貌一致
- **clue_sheet**：場景中出現的線索設計圖
- **上一張分鏡圖**：相鄰片段預設引用，提升畫面連續性
- 當片段標記 `segment_break=true` 時，跳過上一張分鏡圖參考

## Prompt 模板

指令碼從劇本 JSON 讀取以下欄位構建 prompt：

```
場景 [scene_id/segment_id] 的分鏡圖：

- 畫面描述：[visual.description]
- 鏡頭構圖：[visual.shot_type]
- 鏡頭運動起點：[visual.camera_movement]
- 光線條件：[visual.lighting]
- 畫面氛圍：[visual.mood]
- 角色：[characters_in_scene]
- 動作：[action]

風格要求：電影分鏡圖風格，根據專案 style 設定。
角色必須與提供的角色參考圖完全一致。
```

> 畫面比例透過 API 引數設定，不寫入 prompt。

## 生成前檢查

- [ ] 所有角色都有已批准的 character_sheet 影象
- [ ] 場景視覺描述完整
- [ ] 角色動作已指定

## 錯誤處理

- 單場景失敗不影響批次，記錄失敗場景後繼續
- 生成結束後彙總報告所有失敗場景和原因
- 支援增量生成（跳過已存在的場景圖）
- 使用 `--scene-ids` 生成失敗場景
