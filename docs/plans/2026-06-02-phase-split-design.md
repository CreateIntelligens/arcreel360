# 專案階段拆分設計（Phase Split: 6 階段）

**日期**: 2026-06-02
**狀態**: Draft

## 概述

把專案頂部的階段條（GlobalHeader PhaseStepper）從 5 階段重構成 6 階段：

```
現狀：準備中 → 世界觀 → 劇本創作 → 製作中 → 已完成
       setup   worldbuilding scripting production completed

目標：準備中 → 角色場景 → 劇本創作 → 分鏡圖 → 影片 → 已完成
       setup   lorebook    scripting  storyboard video completed
              (取代 worldbuilding)    (拆 production)
```

三處變更：
1. **移除 `worldbuilding`（世界觀）獨立階段**：overview 生成完直接進 `lorebook`，worldbuilding 原本是瞬時過渡態（使用者停不住），故合併。overview 完成度併入 `setup`/`lorebook` 判定。
2. **新增 `lorebook`（角色場景）階段**：角色/線索/場景圖鑑獨立成階段，取代原 worldbuilding 的位置。
3. **`production`（製作中）拆成 `storyboard`（分鏡圖）+ `video`（影片）兩階段**。

## 動機

- 階段條目前把「製作中」混為一談，但實際工作流是「先全部做分鏡圖、再全部做影片」兩個明顯不同的步驟，使用者希望階段條反映這個分界。
- 角色/場景圖鑑製作是獨立的一段工作（生成角色 sheet、線索 sheet、場景 sheet），目前被併進「世界觀」，語意不清。

## 現狀定義鏈（探查結論）

**真相源在後端 `lib/status_calculator.py`**，前端 `GlobalHeader.tsx` 的 `PHASES` 只是顯示標籤；phase 由後端 `calculate_current_phase()` 依資料推導後回傳 `current_phase` 字串。

目前 5 階段判定（`calculate_current_phase`, 124-137 行）：

| 條件 | phase |
|------|-------|
| 無 structured overview | `setup` |
| 有 overview、無任何劇本 generated | `worldbuilding`（角色/線索進度也算這） |
| 部分劇本 generated | `scripting` |
| 全部劇本 generated、未全完成 | `production`（進度看影片完成率） |
| 全部 episode `status=completed` | `completed` |

關鍵資料基礎（已存在，無需新增資料結構）：
- `episodes_stats` 每集已有 `storyboards.{total,completed}` 與 `videos.{total,completed}` 兩組獨立數據（75-76 行）→ 拆分鏡圖/影片的判定基礎已就緒。
- `characters.{total,completed}`、`clues.{total,completed}` 已在 status 計算（209-216 行）；場景圖鑑 `scenes` 為 lorebook 第三類。

## 設計：7 階段判定邏輯

### `calculate_current_phase` 新判定（依序短路）

```
1. 無 structured overview                                  → setup
2. overview 完成、lorebook 未完成                            → lorebook
   （lorebook 未完成 = 角色/線索/場景任一「有項目但 sheet 未全生成」）
3. lorebook 完成、無任何劇本 generated                      → lorebook
4. 有部分劇本 generated（not all）                          → scripting
5. 全部劇本 generated、分鏡圖未全完成                        → storyboard
6. 分鏡圖全完成、影片未全完成                                → video
7. 全部 episode status=completed                           → completed
```

（已移除 worldbuilding：overview 完成即進 lorebook。判定 2、3 都落在 lorebook，差別只在 phase_progress。）

**階段邊界定義：**

- **setup → lorebook 的界線**：以「有無 structured overview」為界。overview 一完成就進 lorebook（不再有 worldbuilding 過渡態）。

- **lorebook 完成判定**：允許某類為空（不是每個故事都有線索/場景）。
  ```
  lorebook 完成 = 每個「有項目的類別」其 sheet 都已生成
                = chars_done==chars_total AND clues_done==clues_total AND scenes_done==scenes_total
  （某類 total==0 視為該類已完成，不阻擋）
  ```
  > 實證：專案 cc3ab5a4 線索=0 但角色=3/場景=3；project-72005855 線索=4。判定不可要求三類都有。

- **storyboard → video 的界線**：以「所有 episode 的分鏡圖是否全生成」為界。
  ```
  storyboard 階段 = 劇本全 generated 且 sum(storyboards.completed) < sum(storyboards.total)
  video 階段      = 分鏡圖全完成 且 sum(videos.completed) < sum(videos.total)
  ```

### `_calculate_phase_progress` 新進度

| phase | 進度公式 |
|-------|---------|
| `setup` | 0.0 |
| `lorebook` | `(chars_done+clues_done+scenes_done) / (chars_total+clues_total+scenes_total)`；分母 0 → 1.0 |
| `scripting` | `scripted / total_episodes` |
| `storyboard` | `sum(storyboards.completed) / sum(storyboards.total)` |
| `video` | `sum(videos.completed) / sum(videos.total)` |
| `completed` | 1.0 |

註：原本 `enrich`（226-228 行）對 worldbuilding 的 phase_progress 特例改掛到 `lorebook`（worldbuilding 已移除）。

### episode 級 status 影響

`episodes_stats` 每集的 `status` 目前有 `draft / in_production / completed`（67 行）。`in_production` 不再細分到 episode 級即可滿足階段條需求（階段條是專案級 phase）。但 summary 的 `in_production` 統計可選擇拆成 `in_storyboard / in_video`（見下方影響面）。

## 影響檔案

| 檔案 | 改動 | 為什麼 |
|------|------|--------|
| `lib/status_calculator.py` | **核心**：`calculate_current_phase` 移除 worldbuilding、加 lorebook/storyboard/video 判定；`_calculate_phase_progress` 加三段進度；新增 scenes 圖鑑完成統計 | phase 真相源 |
| `frontend/src/components/layout/GlobalHeader.tsx` | `PHASES` 陣列改為 6 階段（移除 worldbuilding、加 lorebook/storyboard/video）；`onNavigate` 對應每個新 phase 跳到對應工作區 | 階段條顯示 + 點擊跳轉 |
| `frontend/src/components/pages/projects/ProjectCard.tsx` | phase label 映射表（6-10 行）移除 worldbuilding、加 lorebook/storyboard/video | 專案卡片階段標籤 |
| 後端 status 回傳契約 | `current_phase` 值域新增三個字串；`episodes_summary` 視需要拆 `in_production`→`in_storyboard`/`in_video` | 前端讀的契約 |

## 前端 phase → 工作區跳轉對應

`GlobalHeader.onNavigate` 目前點階段跳到對應 UI。新階段對應：

| phase | 點擊跳到 |
|-------|---------|
| `lorebook` | 角色/線索/場景圖鑑頁（lorebook canvas） |
| `storyboard` | TimelineCanvas 的分鏡圖階段（呼應另一份草案：timeline 內分鏡圖/影片 tab） |
| `video` | TimelineCanvas 的影片階段 |

> 關聯：本拆分若搭配「timeline 內分鏡圖/影片 tab」一起做，頂層 phase 與 timeline 子 tab 可語意對齊。但兩者可獨立實作；本 spec 僅負責頂層階段條。

## 測試計劃

`tests/test_status_calculator.py`（或新增）：
- 各階段判定：構造 7 種 fixture，斷言 `calculate_current_phase` 回正確字串
- lorebook 完成判定：線索=0 時不應卡在 lorebook（cc3ab5a4 情境）
- storyboard→video 邊界：分鏡圖未全完成 → storyboard；全完成、影片未完 → video
- 各階段 phase_progress 數值

前端：
- `GlobalHeader` 7 階段渲染與高亮
- `ProjectCard` 新 phase label 顯示

## 不在本期範圍

- ❌ timeline 內分鏡圖/影片 tab（另一份草案，可獨立實作）
- ❌ episode 級 status 細分（除非 summary 統計需要）

## 已確認決策（2026-06-02）

| 決策 | 結論 |
|------|------|
| `worldbuilding` 是否保留 | **移除**，合併成 6 階段（overview 完成直接進 lorebook） |
| summary `in_production` 是否拆 | **維持不拆**，避免擴大後端契約改動；階段條本身仍能分辨分鏡圖/影片 |
| 階段名稱 | 「角色場景／分鏡圖／影片」 |
