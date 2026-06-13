# 計畫：最終成片版本控制（反覆合成 / 回追版本 / 點開看用了哪幾支影片）

**狀態：Draft**
**目標讀者：冷啟動的執行 AI（無本對話脈絡）。照此文件即可實作,不需再自行探索架構,但需照「驗證」節確認行號未漂移。**

---

## 0. 需求（使用者原話）

1. 「我想試試看我有沒有成功合成」→ 能**反覆合成**而不洗掉前一版。
2. 「可以去回追版本之類的」→ 能**切換 / 回退**到舊版成片。
3. 「希望能點開有細節,是說用哪幾支影片」→ 每個成片版本可**展開**,看出**這一版由哪幾支場景影片合成**。

---

## 1. 現況診斷（已盤點,執行者可信賴）

- **最終成片未進版本系統**：`output/episode_N_final.mp4`。`VersionManager.RESOURCE_TYPES = ("storyboards", "videos", "characters", "clues", "scenes")`（`lib/version_manager.py:32`）**不含 output**。
- **合成是覆蓋式**：compose 端點固定輸出 `episode_N_final.mp4`（`server/routers/project_episodes.py`，`output_filename = episode_final_filename(episode)`），每次合成蓋掉上一版 → 正是阻礙「反覆試 + 比較」的根因。
- **場景影片 `videos/` 已有版本控制與時光機**（前端 `VersionTimeMachine`，resourceType `"videos"`），本計畫**不動它**,只複用其模式。
- **compose script 已知道用了哪些影片**：`agent_runtime_profile/.claude/skills/compose-video/scripts/compose_video.py:247` 從 `script.json` 的 `item.generated_assets.video_clip` 蒐集 `video_paths`，但目前只 `print(f"📹 共 {len(video_paths)} 個影片片段")`（:261），**未輸出清單**。
- **現有 FinalVideoCard**（`frontend/src/components/canvas/timeline/FinalVideoCard.tsx`）只有「重新整理 / 下載」，無版本 UI；它已訂閱 `getEntityRefision('final:episode_N')`，合成後由 `EpisodeActionsBar.handleCompose` invalidate 觸發重抓。

### 既有版本機制接口（複用對象,務必沿用而非另造）

- **`lib/version_manager.py`** `VersionManager(project_path)`：
  - `add_version(resource_type, resource_id, prompt, source_file=None, **metadata) -> int`（:133）— 複製 `source_file` 到 `versions/{resource_type}/{id}_v{N}_{ts}{ext}`，寫 `versions.json` 記錄,回傳新版號。`**metadata` 會原樣存入版本記錄（這正是塞「用了哪幾支影片」的地方）。
  - `get_versions(resource_type, resource_id) -> dict`（:88）、`get_current_version`（:119）、`restore_version(resource_type, resource_id, version, current_file) -> dict`（:362）、`has_versions`（:451）。
  - `EXTENSIONS`（:35）需新增 `"output": ".mp4"`。
  - `RESOURCE_TYPES`（:32）需新增 `"output"`。
- **`server/routers/versions.py`**：
  - `_RESOURCE_FILE_PATTERNS`（:26）`dict[str, (subdir, filename_template)]`，如 `"videos": ("videos", "scene_{id}.mp4")`。需新增 `"output": ("output", "episode_{id}_final.mp4")`。
  - `_resolve_resource_path(resource_type, resource_id, project_path)`（:44）依 pattern 算 `current_file` 與 `file_path`。
  - 既有端點 `GET /projects/{p}/versions/{resource_type}/{resource_id}`（:111）與 `POST .../restore/{version}`（:147）**泛型**,新增 `output` 型別後**自動可用**,無需新端點。
  - `_sync_metadata`（:84）目前針對 characters/clues/storyboards;output 不需 metadata 同步,於 switch 中當作 no-op 即可。
- **前端 `frontend/src/components/canvas/timeline/VersionTimeMachine.tsx`**：
  - props `{ projectName, resourceType, resourceId, onRestore? }`，`ResourceType = "storyboards"|"videos"|"characters"|"clues"|"scenes"`。需擴為加 `"output"`。
  - `getResourcePath(resourceType, resourceId)`（:24）需加 `case "output": return \`output/episode_${resourceId}_final.mp4\``。
  - `getImagePreviewHeightClass`：output 是影片,走影片預覽分支（參考 videos 的處理）。
  - `buildMetaRows(info)`（:51）把版本 metadata 轉成顯示列。需加一列「來源影片」顯示 `info.source_clips`。
  - `VersionInfo` 型別在 `frontend/src/api/types.ts:14`，需加可選欄位 `source_clips?: string[]`。
- **前端 versions API**：`frontend/src/api/versions.ts`（`versionsApi.getVersions/restoreVersion`），泛型吃 `resourceType` 字串,**無需改**（除非型別 union 有限制,屆時放寬到含 `output`）。

---

## 2. 設計決策

- **resource_id 用集數字串**：`resourceType="output"`, `resourceId=String(episode)`。版本檔落在 `versions/output/{episode}_vN_{ts}.mp4`，current 檔仍是 `output/episode_N_final.mp4`（沿用 `episode_final_filename`,前端 FinalVideoCard 的讀取邏輯不變）。
- **合成流程改為「寫 current + 存版本」**：compose 端點成功後,呼叫 `VersionManager.add_version("output", str(episode), prompt=..., source_file=<剛產出的 episode_N_final.mp4>, source_clips=[...])`。current 檔本來就在 `output/`，`add_version` 複製一份進 `versions/`。如此反覆合成 → 每次一個新版本,current 永遠是最新,舊版可回追。
- **「用了哪幾支影片」資料來源**：在 compose 端點 `_prep`/`_run` 階段,後端**自行讀 `script.json`** 取 `generated_assets.video_clip` 清單（與 compose script 同一來源,避免依賴 stdout 解析）。把清單存進 `add_version(..., source_clips=clips)` 的 metadata。
  - 備案（較弱,不建議）：改 compose script 多印一行 `📋 source_clips: a.mp4,b.mp4` 再由端點解析。**首選後端自讀 script**,因為端點已經有 `script_path`，零腳本改動、零解析脆弱性。
- **回退語意**：`restore_version` 把選定版本複製回 `output/episode_N_final.mp4`（current）。沿用既有泛型端點,前端 `onRestore` 後 invalidate `final:episode_N` 讓 FinalVideoCard 重抓。
- **不破壞 legacy**：舊的標題命名成片（`pickFinalVideoFile` 的 legacy 分支）保持原樣,只是不進版本系統。

---

## 3. 實作步驟

### 後端

**3.1 `lib/version_manager.py`**
- `RESOURCE_TYPES`（:32）加 `"output"`。
- `EXTENSIONS`（:35）加 `"output": ".mp4"`。
- 確認 `add_version` 的 `**metadata` 會原樣寫入版本記錄（現況如此,:188 `**metadata`）→ `source_clips` 自動落地,無需改方法。
- 確認 `_ensure_dirs`（:61）會為新型別建 `versions/output/` 目錄（它迴圈 `RESOURCE_TYPES`,自動涵蓋）。

**3.2 `server/routers/versions.py`**
- `_RESOURCE_FILE_PATTERNS`（:26）加 `"output": ("output", "episode_{id}_final.mp4")`。
- `_sync_metadata`（:84）：output 分支 no-op（不需同步 project.json）。
- restore 端點（:147）中 `videos` 專屬的 thumbnail 清除邏輯（:187）對 output 不適用,確保只在 `resource_type == "videos"` 時執行（現況已是 `if resource_type == "videos"`,不會誤觸,確認即可）。

**3.3 `server/routers/project_episodes.py`（compose 端點）**
- `_prep` 已有 `script_path`。新增:讀取 `script.json`，蒐集 `source_clips = [item["generated_assets"]["video_clip"] for item in <scenes/segments> if ...video_clip]`（與 compose_video.py:247 同邏輯;注意 narration/drama 兩種結構,參考 compose script 怎麼遍歷）。
- 合成成功後（目前回傳 `output_path` 之前）,呼叫:
  ```python
  from lib.version_manager import VersionManager
  vm = VersionManager(project_path)
  current_final = project_path / "output" / episode_final_filename(episode)
  if current_final.exists():
      vm.add_version(
          "output", str(episode),
          prompt="",  # 成片無 prompt,可留空或填合成參數摘要
          source_file=current_final,
          source_clips=source_clips,
          duration_seconds=round(elapsed, 2),
      )
  ```
- 回傳值可加 `"version": <new_version>`（前端用得到,可選）。
- 保留現有 `invalidate` 流程（前端 EpisodeActionsBar 已做）。

### 前端

**3.4 `frontend/src/api/types.ts`**
- `VersionInfo`（:14）加 `source_clips?: string[];`。

**3.5 `frontend/src/components/canvas/timeline/VersionTimeMachine.tsx`**
- `ResourceType`（:11）union 加 `"output"`。
- `getResourcePath`（:24）加 `case "output": return \`output/episode_${resourceId}_final.mp4\`;`。
- output 走**影片預覽**分支（參考既有 `videos` 用 `PreviewableVideoFrame` 的路徑,別套圖片預覽）。
- `buildMetaRows`（:51）加:
  ```ts
  if (info.source_clips?.length)
    rows.push({ label: "來源影片", value: info.source_clips.join("、") });
  ```
  → 這就是「點開看用了哪幾支影片」的呈現。

**3.6 `frontend/src/components/canvas/timeline/FinalVideoCard.tsx`**
- 在卡片標題列（:60 那塊 flex）旁,當 `has versions` 時掛上 `<VersionTimeMachine projectName={projectName} resourceType="output" resourceId={String(episode)} onRestore={...} />`。
- `onRestore` 回呼:呼叫 `useAppStore.getState().invalidateEntities([\`final:episode_${episode}\`])`，觸發本卡重抓 current 成片（與合成後同一條重抓路徑）。
- 「重新整理 / 下載」維持不變。

---

## 4. 測試（TDD：先寫測試再實作,符合專案 80% 覆蓋要求）

### 後端（`tests/`）
- `test_version_manager.py`（若無則新增）：`add_version("output", "1", ..., source_clips=[...])` → `get_versions` 回傳含 `source_clips`;`restore_version` 把舊版複製回 current。
- `test_versions_router.py`：`GET /projects/{p}/versions/output/1` 與 `POST .../restore/{v}` 對 output 型別正常運作。
- `test_projects_router.py`（既有,含 compose 測試）：擴充——合成後 `versions/output/` 有新版本記錄,且記錄含 `source_clips`。沿用既有 compose 測試的 mock 模式。

### 前端（vitest）
- `FinalVideoCard.test.tsx`（既有）：有版本時渲染 VersionTimeMachine;restore 後觸發 invalidate/重抓。
- `VersionTimeMachine.test.tsx`（若無則新增最小案例）：`resourceType="output"` 時 `getResourcePath` 正確、`buildMetaRows` 顯示「來源影片」。

---

## 5. 驗證指令（執行者必跑,貼出輸出）

```bash
# 後端
cd /home/human/arcreel360
uv run ruff check . && uv run ruff format --check .
uv run python -m pytest tests/test_version_manager.py tests/test_versions_router.py tests/test_projects_router.py -q
# 全套 + 覆蓋率（CI 門檻 80%）
uv run python -m pytest --cov=lib --cov=server --cov-fail-under=80 -q 2>&1 | tail -15

# 前端
cd frontend
pnpm check   # typecheck + 全套 vitest
```

通過標準：ruff 全過;上述後端測試與前端 `pnpm check` 全綠;覆蓋率 ≥80%。

---

## 6. 範圍邊界（避免越界）

- **不動** `videos/` 既有版本控制與其時光機行為。
- **不動** `pickFinalVideoFile` 的 legacy 標題命名回退（保留向後相容）。
- **不新增** versions 路由端點——既有泛型端點加 `output` 型別即可。
- **首選後端自讀 `script.json` 取 source_clips**,不要為此重寫 compose script 的輸出格式（除非自讀遇到結構障礙,才退用 stdout 方案並在 PR 說明）。
- 不順手改其他 UI / 不擴大到「多集成片」等未要求的功能。

---

## 7. 風險與注意

- **narration vs drama 結構差異**：取 `video_clip` 時兩種 content_mode 的 script 結構不同,務必參照 `compose_video.py` 既有遍歷邏輯（:247 附近）保持一致,別只處理一種。
- **resource_id 一致性**：後端 `str(episode)` 與前端 `String(episode)` 必須一致,否則版本對不上。
- **current 檔來源**：`add_version` 的 `source_file` 要指向**剛合成的 current 成片**,不是 versions 目錄裡的檔。
- **既有測試斷言**：compose 測試若斷言過回傳結構,新增 `version` 欄位時同步更新斷言（屬預期更新,非回歸）。

---

## 8. 完成定義

- 反覆按「合成成片」會累積版本,current 永遠最新,舊版可在成品 tab 的時光機切換 / 回退。
- 每個版本可展開,「來源影片」列出該版用了哪幾支場景影片。
- 第 5 節驗證全過、覆蓋率達標,範圍未越界。
- 計畫狀態保持 Draft,由使用者確認後才標 Done。
```
