# 分鏡層級模型覆蓋設計（Per-Scene Model Override）

**日期**: 2026-05-26
**狀態**: Draft

## 概述

允許使用者為**單一分鏡（scene）**獨立指定圖片後端與影片後端，覆蓋專案層級的預設值。

文字生成（劇本、prompt）**不在本期範圍**，維持專案層級控制。

## 動機

目前 `project.json` 的 `image_backend` / `video_backend` 是專案層級，整個專案內所有分鏡共用同一組模型。實務上使用者希望：

- 某幾個關鍵分鏡用更貴、更高品質的模型
- 動作戲走 Veo、靜態鏡頭走 Lite 模型省成本
- A/B 比對同一個 prompt 在不同模型下的結果

## 設計決策

| 方面 | 決策 |
|------|------|
| 粒度 | scene-level（每個分鏡可獨立設定） |
| 覆蓋類型 | 圖片後端、影片後端（文字暫不支援） |
| 儲存位置 | `episode_*.json` 內每個 scene 物件 |
| 缺省行為 | 欄位缺省或 `null` → 沿用專案層級 |
| 解析順序 | scene → project → global default |
| 後端格式 | `"provider_id/model_id"`（與專案層級一致） |
| 風險提示 | UI 顯示「混用模型可能風格不一致」警語 |

## 資料結構

### Scene 物件新增欄位

```json
{
  "scene_id": "scene_1",
  "description": "...",
  "image_prompt": "...",
  "video_prompt": "...",
  "image_backend": "openai/gpt-image-1",
  "video_backend": null,
  "generated_assets": { ... },
  "duration_seconds": 8
}
```

| 欄位 | 型別 | 說明 |
|------|------|------|
| `image_backend` | `string \| null` | 覆蓋專案 `image_backend`，格式 `"provider/model"`；`null` 或缺省 = 沿用上層 |
| `video_backend` | `string \| null` | 覆蓋專案 `video_backend`，同上 |

### 向後相容

- 既有 `episode_*.json` 不含這兩個欄位 → 行為等同 `null` → 完全沿用專案層級
- `lib/data_validator.py` 將新欄位標記為 `Optional`
- 不需要資料遷移

## 解析鏈

```
scene.image_backend  →  project.image_backend  →  global default
scene.video_backend  →  project.video_backend  →  global default
```

生成入隊時會先將 scene 覆蓋快照進任務 payload；worker 端維持既有解析流程，不在執行時回頭查 episode JSON。

## 後端改動

### 1. 解析層 — `lib/project_manager.py` / `server/routers/generate.py`

`ProjectManager.update_scene_backend()` 負責更新 episode JSON 中的 scene/segment 覆蓋欄位：

```python
pm.update_scene_backend(
    project_name=name,
    script_filename=req.script_file,
    scene_id=scene_id,
    image_backend="openai/gpt-image-1",
)
```

`server/routers/generate.py` 的 `_snapshot_image_backend()` / `_snapshot_video_backend()` 在入隊時依 `script_file + resource_id` 讀取 scene 覆蓋。

### 2. 任務 Payload 快照

入隊時：
- 若 scene 有覆蓋，payload 寫 scene 的 backend
- 否則沿用現有邏輯（讀 project）

這樣 worker 端不必再回頭查 episode JSON。

### 3. API — 新增 endpoint

`server/routers/projects.py`：

```
PATCH /api/v1/projects/{name}/episodes/{n}/scenes/{scene_id}/backend
Body: {
  "image_backend": "openai/gpt-image-1" | null,
  "video_backend": "ark/doubao-seedance-pro" | null
}
```

- 兩個欄位皆 optional，只傳要改的
- 設為 `null` 表示清除覆蓋（回到沿用專案）
- 驗證 `provider/model` 字串：provider 必須存在於 `/api/v1/providers`，model 必須屬於該 provider 的對應 media_type

### 4. 費用預估 — `server/routers/cost_estimation.py`

確認 `_estimate_scene_cost()` 是否已按 scene 傳入的 model 計算。
若目前讀 project-level model，需改成讀 scene 覆蓋優先。

## 前端改動

### 1. SegmentCard 增加模型 selector

**落點**：`frontend/src/components/canvas/timeline/SegmentCard.tsx`
（時間軸 canvas 上的分鏡卡片，使用者實際做生成的地方）

**不動** `frontend/src/components/canvas/lorebook/SceneCard.tsx`
（圖鑑頁是瀏覽用，加 selector 會增加雜訊）

每個分鏡卡片右上角加齒輪 icon，點開 popover：

```
┌─ Scene 1 模型設定 ───────────────┐
│ 🖼  圖片後端                      │
│    [專案預設模型 ▾]               │
│      ├ 專案預設模型               │
│      ├ Gemini Flash Image         │
│      ├ OpenAI GPT-Image-1         │
│      └ Ark SeedDream              │
│                                  │
│ 🎬  影片後端                      │
│    [Veo 3.1 Lite ▾]              │
│                                  │
│ 💰  預估費用：本場景               │
│     圖片 $0.04 → $0.08 (+$0.04)  │
│     影片 $0.12 → $0.12 (沿用)    │
│                                  │
│ ⚠️ 混用模型可能造成風格不一致     │
│                                  │
│ [批次套用到本集所有分鏡]          │
└─────────────────────────────────┘
```

### 2. Provider 清單來源

複用 `/api/v1/providers`，按 `media_type` 過濾：
- 圖片下拉只顯示 `image` 能力的 provider/model 組合
- 影片下拉只顯示 `video` 能力的組合

### 3. 視覺指示

當 scene 有覆蓋（非 `null`）時，卡片標題列顯示小 chip：

```
Scene 1  🖼 OpenAI  🎬 Veo Lite
```

未覆蓋的 scene 不顯示 chip（沿用專案，保持卡片乾淨）。

### 4. 批次套用快捷

popover 底部按鈕：「批次套用到本集所有分鏡」
- 範圍：**本集** 內的其他所有 scene（不跨集數）
- 將當前 scene 的兩個 backend 設定複製到同集其他 scene
- 用於想對整集統一切換但又不想破壞 scene-level 結構的場景
- 不提供「全專案」批次按鈕 — 全專案改變請直接改專案層級 `image_backend` / `video_backend`

### 5. 即時費用差異

打開 popover 或切換下拉選項時，呼叫 `/api/v1/cost-estimation/scene`（若無則新增），
傳入當前 scene + 新 backend，回傳：

```json
{
  "image": { "current": 0.04, "next": 0.08, "delta": 0.04 },
  "video": { "current": 0.12, "next": 0.12, "delta": 0.0 }
}
```

UI 顯示「圖片 $0.04 → $0.08 (+$0.04)」，沿用時顯示「(沿用)」。

## 互動與邊界情形

| 情境 | 行為 |
|------|------|
| Scene 有覆蓋，但該 provider 已停用/未配置 | 任務入隊時驗證失敗，回傳明確錯誤訊息，提示使用者改設定 |
| Scene 設定的 model 不在 provider 的能力清單 | 同上，驗證失敗 |
| 使用者改了專案層級 backend | 已有 scene 覆蓋的不受影響，未覆蓋的自動跟進 |
| 生成既有分鏡 | 使用當下 scene 覆蓋值，不引用歷史版本的 backend |
| 任務已入隊但尚未執行時改 scene backend | 不影響已排隊任務（payload 已快照） |

## 不在本期範圍

- ❌ 文字生成 per-scene 模型（劇本目前是整集生成，沒有 scene 概念，需另設計）
- ❌ Episode-level 覆蓋層（如未來需要可再加，回退鏈擴成 `scene → episode → project`）
- ❌ 歷史版本記錄 backend 切換歷程（VersionManager 已記錄每次生成的 model，足夠回溯）

## 工時估算

| 階段 | 工時 |
|------|------|
| 後端解析與 payload 快照 | 0.3 天 |
| API endpoint + 驗證 | 0.2 天 |
| 前端 scene 卡片 selector | 0.3 天 |
| Provider 清單過濾與批次套用 | 0.2 天 |
| 測試（解析鏈、API、UI） | 0.3 天 |
| **總計** | **1.3 天** |

## 測試計劃

### 後端

- `tests/test_scene_backend_override.py`：
  - scene 有覆蓋 → 任務 payload 採用 scene backend
  - scene 無覆蓋 → 沿用 project backend
  - 清除覆蓋時移除欄位並回到上層設定
- `tests/lib/test_cost_estimation.py` 或 router 測試驗證 scene 覆蓋下費用計算正確

### 前端

- `frontend/src/components/.../SceneCard.test.tsx`：
  - 顯示 chip 條件
  - popover 切換後正確 PATCH
  - 「專案預設模型」選項清除覆蓋
- E2E：建立專案 → 設定某分鏡用不同模型 → 觸發生成 → 驗證 task 使用該 model

## 已確認決策（2026-05-26）

| 決策 | 結論 |
|------|------|
| UI 落點 | 只動 `SegmentCard.tsx`（timeline），不動 `SceneCard.tsx`（lorebook） |
| 批次套用範圍 | 本集；全專案改變走專案層級設定 |
| 費用即時顯示 | 開啟 popover 與切換選項時顯示「current → next (delta)」 |
