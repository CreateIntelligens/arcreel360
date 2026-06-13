# 劇集層級模型覆蓋設計（Per-Episode Model Override）

**日期**: 2026-06-01
**狀態**: Draft

## 概述

在既有的 [分鏡層級模型覆蓋](2026-05-26-per-scene-model-override-design.md) 之上，補上**劇集（episode）層級**的生成設定覆蓋層，把回退鏈從 `scene → project → global` 擴成：

```
scene → episode → project → global default
```

本期延續前期範圍：圖片後端、影片後端與相關生成參數（解析度、時長），文字生成不在範圍。

## 動機

前期 scene-override 設計（`2026-05-26-...-design.md` 第 200 行）已明確預留此延伸：

> ❌ Episode-level 覆蓋層（如未來需要可再加，回退鏈擴成 `scene → episode → project`）

實務缺口（使用者回報）：

- 影片生成時 model 實際只走 `scene → project.video_backend → 寫死 veo`，**完全沒有 episode 層**。
- 想對「整集」統一指定 model（例如第 2 集全部走 Seedance、第 3 集全部走 Veo），目前只能逐個 scene 設定，或被迫改動全專案預設。
- scene 未設、episode 也無從設定時，直接掉到全域或寫死的 `veo-3.1-lite-generate-preview`，這正是「沒吃到我為某分鏡的設定，吃了預設 veo」的根因。

## 現狀盤點（bug 確認）

`server/services/generation_tasks.py::execute_video_task` 目前的回退鏈：

| 參數 | 現有回退鏈 | 缺口 |
|------|-----------|------|
| provider/model | `payload.video_provider`(scene) → `project.video_backend`(global) → `resolver.default_video_backend()` → 寫死 `gemini-aistudio/veo-3.1-lite-generate-preview` | ❌ 無 episode 層 |
| resolution | `payload.video_resolution`(scene) → `project.video_model_settings[model].resolution`(global) → provider 預設 | ❌ 無 episode 層 |
| duration | `payload.duration_seconds`(scene/req) → `project.default_duration`(global) → model 預設 | ❌ 無 episode 層 |
| image backend | `payload.image_provider/model`(scene) → `project.image_backend`(global) → global 預設 | ❌ 無 episode 層 |
| image size | `payload.image_size`(scene) → 預設 `1K` | ❌ 無 episode 層 |

- **scene 層**存在劇本 JSON 每個 storyboard item 上（`video_backend` / `image_backend` / `video_resolution` / `image_size` 等欄位），於入隊路由 `generate.py` 的 `_snapshot_video_backend` / `_snapshot_image_backend` 讀出後快照進 payload。
- **global 層**存在 `project.json`（`video_backend` / `image_backend` / `video_model_settings` / `default_duration`）。
- **episode 層**：`project.json` 的 episode 物件目前只有 `{episode, title, script_file, order}`，沒有任何生成設定欄位，程式碼無任何一處讀取 episode 級設定。

## 設計決策

| 方面 | 決策 |
|------|------|
| 粒度 | episode-level（每集可獨立設定，介於 scene 與 project 之間） |
| 覆蓋類型 | 圖片後端、影片後端、解析度、時長（與 scene 層對齊；文字暫不支援） |
| 儲存位置 | `project.json` 的 episode 物件下，集中於 `overrides` 子物件 |
| 缺省行為 | `overrides` 缺省、為 `null`，或子欄位缺省 → 沿用上層（project → global） |
| 解析順序 | `scene → episode → project → global default` |
| 後端格式 | `"provider_id/model_id"`（與 scene / project 層一致） |
| 插入位置 | **入隊路由 `generate.py`**（與 scene 覆蓋同一解析點） |

### 為何把 episode 讀取放在入隊路由（而非服務層）

1. **單一解析點**：scene 覆蓋已在 `generate.py` 解析完才塞 payload。episode 層放同處，整條 `scene → episode → project` 鏈集中於一個函式，避免 fallback 邏輯散落在路由層、服務層、resolver 三處（那正是現有混亂來源）。
2. **拿得到 episode 編號**：路由層有 `script_file` + `project`，episode 物件本就以 `script_file` 對應（`ProjectManager.update_episode` 用 `script_file` 當 key），由 `script_file` 反查 episode 是現成的。服務層 `execute_video_task` 反而要從 `script_file` 再反查 episode，較繞。
3. **行為一致 / 不影響已排隊任務**：image 與 video 兩條入隊路徑共用同一 snapshot 模式，episode 層加上去兩邊自然一致；payload 已快照，已入隊任務不受後續 episode 設定變動影響（與 scene 層相同語意）。

## 資料結構

### Episode 物件新增 `overrides` 子物件

```json
{
  "episode": 2,
  "title": "...",
  "script_file": "scripts/episode_2.json",
  "order": 1,
  "overrides": {
    "video_backend": "ark/doubao-seedance-pro",
    "image_backend": null,
    "video_resolution": "1080p",
    "image_size": null,
    "duration_seconds": 8
  }
}
```

| 欄位 | 型別 | 說明 |
|------|------|------|
| `overrides.video_backend` | `string \| null` | 覆蓋 project `video_backend`，格式 `"provider/model"`；`null`/缺省 = 沿用上層 |
| `overrides.image_backend` | `string \| null` | 覆蓋 project `image_backend`，同上 |
| `overrides.video_resolution` | `string \| null` | 覆蓋 project 解析度 |
| `overrides.image_size` | `string \| null` | 覆蓋 image_size |
| `overrides.duration_seconds` | `int \| null` | 覆蓋 project `default_duration` |

未設的 key 一律 fallback 上層；`overrides` 整個缺省等同全部沿用 project。

### 向後相容

- 既有 `project.json` 的 episode 不含 `overrides` → 行為等同全部 `null` → 完全沿用 project 層。
- `lib/data_validator.py` 將 `overrides` 及其子欄位標記為 `Optional`。
- 不需要資料遷移。

## 解析鏈

```
model:       scene.video_backend → episode.overrides.video_backend → project.video_backend → global default
             scene.image_backend → episode.overrides.image_backend → project.image_backend → global default
resolution:  scene.video_resolution → episode.overrides.video_resolution → project.video_model_settings → provider 預設
duration:    scene/req.duration_seconds → episode.overrides.duration_seconds → project.default_duration → model 預設
image_size:  scene.image_size → episode.overrides.image_size → 預設 1K
```

入隊時於 `generate.py` 將「scene 覆蓋優先、否則 episode 覆蓋」的結果快照進 payload；worker 端維持既有解析流程，不在執行時回頭查 project.json。

## 後端改動

### 1. 解析層 — `server/routers/generate.py`

新增 helper：依 `script_file` 反查 episode 物件，讀其 `overrides`：

```python
def _read_episode_override(project: dict, script_file: str | None, field: str) -> str | None:
    """讀取 episode-level 覆蓋；scene 未設時的下一層。"""
    if not script_file:
        return None
    for ep in project.get("episodes", []):
        if ep.get("script_file") == script_file:
            ov = ep.get("overrides") or {}
            value = ov.get(field)
            return value if isinstance(value, str) and value.strip() else None
    return None
```

調整 `_snapshot_video_backend` / `_snapshot_image_backend`：在「scene 覆蓋為 None」時，改讀 episode 覆蓋，再 fallback 到既有 project 邏輯。維持回傳 payload patch 的既有介面，worker 端不需改。

`duration_seconds` / `video_resolution` / `image_size` 三個非 backend 欄位同樣在 snapshot 階段補 episode fallback（目前 scene 未設時為空、直接落到服務層讀 project；改為 scene → episode → 留空交服務層讀 project）。

### 2. 服務層 — `server/services/generation_tasks.py`

維持既有解析流程（payload → project → 預設）。因 episode 層已在入隊時快照進 payload，**服務層不需改動**，回退鏈自然變成 `scene/episode(payload) → project → 預設`。

> 註：寫死的 `"gemini-aistudio", "veo-3.1-lite-generate-preview"`（第 775 行）保留為 resolver 全失敗時的最終保險，不在本期移除。

### 3. API — 新增 episode 覆蓋 endpoint

`server/routers/projects.py`（或 `project_episodes.py`）：

```
PATCH /api/v1/projects/{name}/episodes/{n}/overrides
Body: {
  "video_backend": "ark/doubao-seedance-pro" | null,
  "image_backend": "openai/gpt-image-1" | null,
  "video_resolution": "1080p" | null,
  "image_size": null,
  "duration_seconds": 8 | null
}
```

- 所有欄位 optional，只傳要改的；設為 `null` 清除該層覆蓋（回到沿用 project）。
- 驗證 `provider/model`：provider 必須存在於 `/api/v1/providers`，model 屬於該 provider 對應 media_type（複用 scene endpoint 既有驗證）。

### 4. 費用預估 — `server/routers/cost_estimation.py`

`_project_video_resolution` / `_estimate_scene_cost` 等目前讀 `scene → project`。補 episode 層：scene 未設時讀 episode override，再 fallback project，使預估與實際生成一致。

## 前端改動

### 1. 劇集設定入口

在**集數標題列**放一個 chip 作為入口，點開 Popover（與 scene 卡片的齒輪 popover 同一套互動模式，使用者心智一致，不另開獨立面板）：

```
┌─ 第 2 集 模型設定 ───────────────┐
│ 🖼  圖片後端  [專案預設模型 ▾]    │
│ 🎬  影片後端  [Seedance Pro ▾]   │
│ 📐  解析度    [1080p ▾]          │
│ ⏱  時長      [8 秒 ▾]           │
│                                  │
│ ⚠️ 本集設定會覆蓋專案預設，       │
│    但仍可被個別分鏡再覆蓋         │
└─────────────────────────────────┘
```

### 2. 視覺指示與層級關係

- episode 有覆蓋時，集數標題列顯示 chip（如 `第2集 🎬 Seedance`）。
- scene 卡片的「沿用」語意改為「沿用上層」=（episode 有設則顯示 episode 值，否則 project 值），讓使用者看得出三層關係。

### 3. Provider 清單來源

複用 `/api/v1/providers`，按 `media_type` 過濾，與 scene selector 同一套元件。

## 互動與邊界情形

| 情境 | 行為 |
|------|------|
| scene 有覆蓋 + episode 也有覆蓋 | scene 優先 |
| scene 無覆蓋 + episode 有覆蓋 | 用 episode |
| scene/episode 皆無 | 用 project，再 fallback global/寫死 |
| episode 覆蓋的 provider 已停用 | 入隊驗證失敗，回明確錯誤 |
| 改 project 層 backend | 已設 episode/scene 覆蓋者不受影響，未覆蓋者自動跟進 |
| 任務已入隊後改 episode 覆蓋 | 不影響已排隊任務（payload 已快照） |

## 不在本期範圍

- ❌ 文字生成 per-episode 模型（劇本整集生成，需另設計）
- ❌ 移除服務層寫死的最終保險值
- ❌ episode 覆蓋的歷史版本記錄（VersionManager 已記錄每次生成的 model）

## 工時估算

| 階段 | 工時 |
|------|------|
| 後端解析（generate.py episode fallback） | 0.3 天 |
| API endpoint + 驗證 | 0.2 天 |
| 費用預估補 episode 層 | 0.2 天 |
| 前端 episode 設定 UI | 0.3 天 |
| 測試（解析鏈、API、費用） | 0.3 天 |
| **總計** | **1.3 天** |

## 測試計劃

### 後端

- `tests/test_episode_backend_override.py`：
  - scene 有覆蓋 → payload 採 scene（episode 被略過）
  - scene 無覆蓋、episode 有覆蓋 → payload 採 episode
  - scene/episode 皆無 → payload 不含覆蓋，服務層讀 project
  - 清除 episode 覆蓋 → 回到 project 設定
  - 四參數（backend / resolution / duration / image_size）各驗證一次三層 fallback
- 費用預估：episode 覆蓋下預估與實際生成 model 一致

### 前端

- episode 設定 popover：切換後正確 PATCH、清除回到沿用
- E2E：建立專案 → 設第 2 集統一某 model → 觸發某未設 scene 的生成 → 驗證 task 使用 episode model（而非寫死 veo）

## 已確認決策（2026-06-02）

| 決策 | 結論 |
|------|------|
| 前端 episode 設定 UI 落點 | **集數標題列 chip + Popover**（與 scene 齒輪 popover 同一套互動，不另開面板） |
| `overrides` 是否一併納入 image 參數 | **納入**：含 image_backend / image_size，與 scene/global 兩層一致，避免三層 fallback 在圖片上斷裂 |
