# 統一專案風格注入設計（Unified Project Style）

**日期**: 2026-06-04
**狀態**: Draft

## 概述

把「專案風格」收攏成單一真相源，並補齊風格注入的破口。目前三個風格輸入分散、各自餵到不同生成、且彼此不一致：

- `style`（風格標籤，如 `Anime`）：**只能在建立專案時選一次**，之後 UI 無法編輯；卻是**唯一會餵進分鏡圖**的欄位。
- `style_description`（AI 分析 / 手動編輯的描述文字，UI 上那段約 300 字）：總覽頁可編輯；但**分鏡圖與影片都吃不到**。
- `style_image`（風格參考圖）：總覽頁可上傳/替換/刪除；上傳當下被分析成 `style_description`，圖片本身不參與後續生成。

結果是**使用者能編輯的（描述）影響不到分鏡，能影響分鏡的（style 標籤）又改不了**。本設計修掉這個錯位。

## 目標

1. **`style` 標籤從「建立時選一次」變成總覽頁可編輯** —— 三個風格輸入（標籤 / 參考圖 / 描述）收攏到同一塊「專案風格」UI，成為單一真相源。
2. **所有圖片生成統一吃「`style` + `style_description` 合併後」的風格**：角色 / 線索 / 場景 / **分鏡圖**。
3. **影片不額外餵風格** —— 影片以分鏡圖為首幀（`start_image`），視覺風格自分鏡圖繼承。
4. **參考圖圖片本身不當 reference image 餵入生成** —— 維持現狀，只在上傳當下被分析成描述（文字注入，非圖片注入）。

## 不在本期範圍

- ❌ 把 `style_image` 當 reference image 餵進角色/分鏡生成（已決定不做，採純文字統一調性）。
- ❌ 影片 prompt 注入風格描述（已決定靠分鏡圖首幀繼承）。
- ❌ overview / 劇本等純文字生成注入視覺風格（產出為文字，不適用）。

## 現狀定義鏈（探查結論）

### 資料欄位（`project.json`）

| 欄位 | 內容 | UI 入口 |
|------|------|---------|
| `style` | 短標籤，如 `"Anime"` / `"Photographic"` / `"3D Animation"` | **建立專案 modal**（`CreateProjectModal.tsx`） |
| `style_image` | 參考圖檔名，如 `style_reference.png` | 總覽頁「專案風格」區（`OverviewCanvas.tsx`） |
| `style_description` | 約 300 字風格描述 | 總覽頁「專案風格」區（`OverviewCanvas.tsx`） |

### 後端注入點現狀

| 生成類型 | 程式位置 | 目前吃到什麼 |
|---------|---------|------------|
| 角色圖 | `server/services/generation_tasks.py:889-890` → `build_character_prompt(id, prompt, style, style_desc)` | ✅ `style` + `style_description`（`Visual style:` 前綴） |
| 線索圖 | `generation_tasks.py:939-940` → `build_clue_prompt(...)` | ✅ 同上 |
| 場景圖 | `generation_tasks.py:982-983` → `build_scene_prompt(...)` | ✅ 同上 |
| 分鏡圖 | `generation_tasks.py:673` → `_normalize_storyboard_prompt(prompt, _project.get("style", ""))` | ⚠️ **只有 `style`**，吃不到 `style_description` |
| 影片 | `generation_tasks.py` `_normalize_video_prompt(prompt)`（約 :751） | ❌ 完全不吃（本期維持不吃） |

### 既有可複用元件

- `lib/prompt_builders.py:162` `build_style_prompt(project_data)`：**已經會合併** `style` + `style_description`，輸出：
  ```
  Style: Anime
  Visual style: High-key lighting, soft diffused studio illumination...
  ```
  目前沒有被分鏡圖路徑使用 —— 本設計讓它成為唯一風格字串來源。
- `lib/prompt_utils.py:36` `image_prompt_to_yaml(image_prompt, project_style)`：分鏡圖把 `project_style` 塞進 YAML 的 `Style:` 欄位。本設計只改「傳進去的 `project_style` 內容」，YAML 結構不變。
- `server/routers/files.py:729` `PATCH /projects/{name}/style-description`：手動更新描述的 endpoint。新增的 `style` endpoint 沿用此模式。
- `frontend/src/components/pages/CreateProjectModal.tsx:10-15` `STYLE_OPTIONS`：風格下拉選項（寫實攝影 / 動漫風格 / 3D 動畫）。抽成共用常數供總覽頁複用。

## 設計

### 1. 資料層：單一真相源

三個風格輸入全部可在總覽頁「專案風格」區編輯：

| 欄位 | 改後行為 |
|------|---------|
| `style` | **新增** 總覽頁下拉可編輯（選項同 `STYLE_OPTIONS`）；建立 modal 仍保留作為初始值入口 |
| `style_image` | 不變 |
| `style_description` | 不變 |

### 2. 生成端：統一吃合併風格

**統一接點**：`build_style_prompt(project_data)` 成為唯一產風格字串的函式，圖片三類 + 分鏡圖都走它。

**① 角色 / 線索 / 場景圖（微調，去重）**

現在各 builder 各自拼 `Visual style:` 前綴（`prompt_builders.py:38-39, 106-107, 134-136`）。改成統一呼叫 `build_style_prompt(project_data)` 產生風格前綴，消除重複邏輯。行為等價（合併結果相同），只是收斂到一處。

> 實作注意：`build_character_prompt` 等目前簽名是 `(name, description, style, style_description)`。可在呼叫端（`generation_tasks.py`）改為先算 `build_style_prompt(_project)` 再傳入，或讓 builder 內部呼叫 `build_style_prompt`。擇一即可，重點是「只有一處合併邏輯」。

**② 分鏡圖（主要破口，必改）**

- 現在：`generation_tasks.py:673`
  ```python
  _prompt_text = _normalize_storyboard_prompt(_effective_prompt, _project.get("style", ""))
  ```
  → YAML `Style:` 欄位只有 `"Anime"`。

- 改後：
  ```python
  _combined_style = build_style_prompt(_project)   # "Style: Anime\nVisual style: ..."
  _prompt_text = _normalize_storyboard_prompt(_effective_prompt, _combined_style)
  ```
  → `_normalize_storyboard_prompt`（`generation_tasks.py:359`）內部呼叫 `image_prompt_to_yaml(normalized_prompt, style)`（`:382`），`style` 參數即為合併字串，塞進 YAML 的 `Style:` 欄位。

  **YAML 結構不變**，只是 `Style:` 欄位內容從一個詞變成完整風格：
  ```yaml
  Style: |
    Style: Anime
    Visual style: High-key lighting, soft diffused studio illumination...
  Scene: 男主角站在窗邊...
  Composition: {...}
  ```

  > 注意：`_normalize_storyboard_prompt` 收到 `str` 型 prompt 時會直接回傳（`:360-361`），此時風格不經 YAML。需確認字串型 prompt 是否也要補風格 —— 若要，於字串分支也拼上 `_combined_style` 前綴。實作時依現有 prompt 多為結構化的事實處理；若字串型 prompt 罕見，可於該分支加 `Visual style:` 前綴對齊圖片類做法。

**③ 影片（不動）**

維持 `_normalize_video_prompt(prompt)` 不注入風格。影片以分鏡圖（`storyboards/scene_{id}.png`）為 `start_image`，風格自首幀繼承。

### 3. 前端：總覽頁加風格下拉

- **抽共用常數**：把 `CreateProjectModal.tsx:10-15` 的 `STYLE_OPTIONS` 抽到共用位置（如 `frontend/src/utils/project-style.ts` 或既有 constants 檔），兩處 import 同一份。
- **總覽頁 UI**：`OverviewCanvas.tsx` 的「專案風格」區（約 :160 起），在參考圖區塊上方加一個風格下拉選單：
  - 顯示當前 `projectData.style`，選項為 `STYLE_OPTIONS`。
  - onChange → 呼叫 `API.updateStyle(projectName, value)`（新增的 API client method）。
  - 成功後 `refreshProject()` + toast（對齊既有 `style_description` 儲存流程，`OverviewCanvas.tsx:129`）。
- **API client**：`frontend/src/api/projects.ts` 新增 `updateStyle(projectName, style)` → `PATCH /projects/{name}/style`。
- 建立 modal 維持原樣（仍可選初始風格）。

### 4. 後端：新增 update_style endpoint

`server/routers/files.py` 新增（複製 `update_style_description`，`:729-745` 的模式）：

```python
@router.patch("/projects/{project_name}/style")
async def update_style(
    project_name: str, _user: CurrentUser, style: str = Body(..., embed=True)
):
    def _sync():
        project_data = get_project_manager().load_project(project_name)
        project_data["style"] = style
        with project_change_source("webui"):
            get_project_manager().save_project(project_name, project_data)
        return {"success": True, "style": style}
    return await asyncio.to_thread(_sync)
```

> 可考慮加入白名單驗證（`style in {"Photographic", "Anime", "3D Animation"}`），避免任意字串寫入。

## 影響檔案

| 檔案 | 改動 | 為什麼 |
|------|------|--------|
| `server/services/generation_tasks.py` | 分鏡圖路徑（:673）改用 `build_style_prompt`；角色/線索/場景（:889/939/982）收斂到 `build_style_prompt` | 補分鏡圖破口 + 去重 |
| `lib/prompt_builders.py` | `build_style_prompt` 成為唯一風格字串來源（既有函式，可能微調） | 單一合併邏輯 |
| `server/routers/files.py` | 新增 `PATCH /projects/{name}/style` | style 可編輯 |
| `frontend/src/components/pages/CreateProjectModal.tsx` | `STYLE_OPTIONS` 抽成共用常數 | 前端去重 |
| `frontend/src/components/canvas/OverviewCanvas.tsx` | 「專案風格」區加風格下拉 + 儲存流程 | style 可編輯 UI |
| `frontend/src/api/projects.ts` | 新增 `updateStyle` | 對接新 endpoint |
| `frontend/src/utils/project-style.ts`（新）或既有 constants | `STYLE_OPTIONS` 共用 | 前端去重 |

## 測試計劃

**後端**
- `build_style_prompt`：`style` + `style_description` 兩者皆有時合併；缺一時的退化（只有 `style` / 只有描述 / 都沒有）。
- 分鏡圖 normalize：結構化 prompt 經 `_normalize_storyboard_prompt(prompt, build_style_prompt(project))` 後，YAML `Style:` 欄位含描述文字（非僅標籤）。
- 新 endpoint：`PATCH /projects/{name}/style` 寫入 `project.json` 並回傳；（若加白名單）非法值被拒。

**前端**
- `OverviewCanvas.test.tsx`：風格下拉渲染當前 `style`；選擇後呼叫 `API.updateStyle` 並觸發 refresh。

## 已確認決策（2026-06-04）

| 決策 | 結論 |
|------|------|
| 參考圖圖片是否當 reference image 餵入生成 | **否**，只用文字描述統一調性（方案 B） |
| 影片是否注入風格描述 | **否**，靠分鏡圖首幀繼承 |
| 只補破口 vs 統一風格欄位 | **統一**：把 `style` 拉到總覽頁可編輯，三輸入收攏成單一真相源 |
| 分鏡圖注入方式 | 沿用 YAML `Style:` 欄位，內容換成 `build_style_prompt` 合併字串（結構不變） |
