# 生成參數四項修復 — 執行指令

> 狀態：Draft（待執行）
> 日期：2026-05-29
> 對象：交付給執行 AI。每項都附根因、精確檔案/行號、修改方式、驗收標準。
> 重要：所有根因已查證確認，非臆測。請嚴格按指令改，勿擴大範圍。

---

## 通用規範

- 後端 lint：`uv run ruff check <file>`，需 All checks passed。
- 前端型別：`cd frontend && pnpm exec tsc --noEmit`，需無錯。
- 測試：後端 `uv run python -m pytest <test>`；前端 `pnpm exec vitest run <test>`。
- 每項改完跑對應驗收，全綠才算完成。

---

## 修復 ① 影片選 Seedance 卻用 Veo（最關鍵）

### 根因（已確認）
`server/services/generation_tasks.py` 的 `_resolve_video_backend()`（約 line 236-272）**完全忽略 payload**。
它只從 `project.json` 的 `video_backend` 解析 provider/model（line 256），從不讀分鏡覆蓋寫進 payload 的
`payload["video_provider"]` / `payload["video_provider_settings"]`。

對比圖片路徑 `get_media_generator()`（約 line 295）有：
```python
if payload and payload.get("image_provider"):
    image_provider_id = payload["image_provider"]
    image_model = payload.get("image_model", "") or image_model
```
影片缺這段 → 分鏡選的 Seedance 被丟掉，永遠回退成 project 預設（Veo）。

分鏡覆蓋寫入 payload 的 key（由 `server/routers/generate.py` 的 `_snapshot_video_backend` 產生）：
```python
{"video_provider": provider, "video_provider_settings": {"model": model}}
```

### 修改
在 `_resolve_video_backend()` 內，於「從 project.json 解析」之前，**優先讀 payload**。
目前邏輯（約 line 251-270）：
```python
    if payload:
        project = await asyncio.to_thread(get_project_manager().load_project, project_name)
        provider_name, project_model = _parse_project_backend(project.get("video_backend"))
        if not provider_name:
            provider_name = default_video_provider_id
            mapped = _PROVIDER_ID_TO_BACKEND.get(provider_name, provider_name)
            if mapped == PROVIDER_GEMINI:
                video_backend_type = "vertex" if default_video_provider_id == "gemini-vertex" else "aistudio"
        provider_settings: dict = {"model": project_model} if project_model else {}
        video_backend = await _get_or_create_video_backend(
            provider_name, provider_settings, resolver, default_video_model=video_model,
        )
```

改為：payload 的 `video_provider` 最優先，其次 project，其次全域預設。
```python
    if payload:
        # 優先序：payload 分鏡覆蓋 > project.json > 全域預設
        payload_provider = payload.get("video_provider")
        payload_model = (payload.get("video_provider_settings") or {}).get("model")

        if payload_provider:
            provider_name = payload_provider
            project_model = payload_model
        else:
            project = await asyncio.to_thread(get_project_manager().load_project, project_name)
            provider_name, project_model = _parse_project_backend(project.get("video_backend"))

        if not provider_name:
            provider_name = default_video_provider_id
            mapped = _PROVIDER_ID_TO_BACKEND.get(provider_name, provider_name)
            if mapped == PROVIDER_GEMINI:
                video_backend_type = "vertex" if default_video_provider_id == "gemini-vertex" else "aistudio"

        provider_settings: dict = {"model": project_model} if project_model else {}
        video_backend = await _get_or_create_video_backend(
            provider_name, provider_settings, resolver, default_video_model=video_model,
        )
```

注意：`provider_name` 可能是新格式（`byteplus`/`custom-N`）；`_get_or_create_video_backend` 內已用
`normalize_provider_id` + `is_custom_provider` 處理，無需額外轉換。

### 連帶確認（同檔 execute_video_task）
`execute_video_task`（約 line 734-766）算 `provider_name`/`model_name` 供 resolution/duration fallback，
它**已經**有讀 `payload.get("video_provider")`（line 738）。修 ① 後兩條路徑一致，無需再改。

### 驗收
- 新增測試（可放 `tests/test_generation_tasks.py` 或新檔）：mock payload 帶 `video_provider="byteplus"` +
  `video_provider_settings={"model":"<seedance-model>"}`，斷言 `_resolve_video_backend` 回傳的 backend
  其 `.model` / provider 為 Seedance，而非 project.json 的 Veo。
- 既有 `tests/test_generate_router.py`、`tests/test_generation_tasks.py`（若有）全綠。
- 手動：分鏡選 Seedance 生影片，docker log 應出現 Seedance/byteplus 的 API 呼叫（這也解掉「沒有 log」——
  先前 log 缺失是因為實際走 Veo 且使用者在找 Seedance 的 log）。

---

## 修復 ② 秒數 / 解析度沒跟分鏡模型變

### 根因（已確認）
`SegmentCard.tsx` 內部邏輯本身正確（`effectiveVideoBackend = segment.video_backend || videoBackend`，
並餵進 `useVideoResolutionOptions` / `useVideoDurationOptions`）。
**問題在 prop 覆蓋**：
- `SegmentCard.tsx` 約 line 1157：
  `const effectiveDurationOptions = durationOptions ?? dynamicDurationOptions ?? DEFAULT_DURATIONS;`
  `durationOptions` 是 `TimelineCanvas.tsx` line 440 傳入的**專案級** prop。只要它有值，
  分鏡自算的 `dynamicDurationOptions` 永遠被蓋掉 → 秒數選項不隨分鏡模型變。
- 解析度的「目前值」`effectiveResolution = segment.video_resolution ?? currentResolution`
  （line 1145），`currentResolution` 是專案級 prop，未設 per-scene 覆蓋時退回專案級（這部分可接受，
  但需確認選項 `resolutionOptions` 用 effectiveVideoBackend 算 → 已正確）。

### 修改
`frontend/src/components/canvas/timeline/SegmentCard.tsx`：
讓**分鏡自算值優先於專案級 prop**。將 line 1157 改為分鏡優先：
```typescript
const effectiveDurationOptions = dynamicDurationOptions ?? durationOptions ?? (DEFAULT_DURATIONS as number[]);
```
（交換 `dynamicDurationOptions` 與 `durationOptions` 的順序。）

並確認 `effectiveDurationReason`（line 1158-1160）對應使用分鏡的 `effectiveResolution`（已正確，無需改）。

> 注意：不要移除 `durationOptions` prop（其他呼叫點或唯讀情境仍可能用到它作 fallback）。只調整優先順序。

### 驗收
- 既有 `frontend/src/components/canvas/timeline/SegmentCard.test.tsx` 全綠（12+ 例）。
- 新增測試：給 SegmentCard 一個 `segment.video_backend` = 某 Seedance 模型（supported_durations 與專案級不同），
  同時傳專案級 `durationOptions`，斷言秒數選擇器顯示的是**分鏡模型**的選項，非專案級。
  （需 mock `API.getProviders` 回傳含該 Seedance 模型的 capabilities，參考
  `src/hooks/useVideoResolutionOptions.test.tsx` 的 mock 模式。）

---

## 修復 ③ 費用幣別統一為 USD

### 根因（已確認）
後端 `lib/cost_calculator.py` 各 provider 回傳不同幣別：
- BytePlus / ARK（Seedance）→ `"CNY"`（line 213, 299, 376）
- Gemini / Grok / OpenAI → `"USD"`
前端 `frontend/src/utils/cost-format.ts` 的 `formatCost` 用幣別 code 當 key，
`CNY` 經 `Intl.NumberFormat` 顯示成 `CN¥`，混用模型時出現雙幣別。

### 決策（使用者已定）
統一顯示 **USD**，匯率**寫死常數**。

### 修改（後端換算，單一真相源）
在 `lib/cost_calculator.py` 加一個 CNY→USD 換算常數與 helper，讓所有 `calculate_*` 回傳的
currency 統一為 `"USD"`，金額換算後回傳。**在計算層統一**，前端就不必改。

1. 在檔案頂部常數區加：
```python
# CNY → USD 換算匯率（寫死；如需可調日後移至設定）
CNY_TO_USD_RATE = 1 / 7.2  # 約當 USD/CNY = 7.2
```
2. 加 helper：
```python
def _to_usd(amount: float, currency: str) -> tuple[float, str]:
    """將金額統一換算為 USD。未知幣別原樣回傳。"""
    if currency == "USD":
        return amount, "USD"
    if currency == "CNY":
        return amount * CNY_TO_USD_RATE, "USD"
    return amount, currency
```
3. 在每個對外回傳 `(amount, currency)` 的方法 return 前套用 `_to_usd(...)`。
   涉及方法（依現有 return 行）：line 213、299、314、333、354、372、396 等所有
   `return ..., "CNY"` 與 `return ..., "USD"` 的出口。最穩妥：在這些 return 統一包成
   `return _to_usd(amount, "CNY")` / `return _to_usd(per_image * n, "USD")` 等。

> 若擔心遺漏，可改為在更上層（`server/services/cost_estimation.py` 的 `_add_cost`）統一換算：
> `_add_cost(target, *_to_usd(amount, currency))`。二擇一，**不要兩層都做**（會雙重換算）。
> 建議選 `cost_calculator` 出口層，因為實際用量記錄（usage_tracker）也讀這裡，較一致。
> 請執行 AI 先確認哪些路徑會寫 currency，避免有路徑漏換算或雙重換算。

### 驗收
- `tests/` 中 cost 相關測試（搜 `calculate_cost` / `cost_calculator` / `cost_estimation`）全綠；
  若測試斷言了 `"CNY"`，需同步更新為換算後 USD（這是預期變更，非破壞）。
- 前端費用顯示不再出現 `CN¥`，混用模型也只顯示單一 `$` USD。
- WebUI 用量頁（/usage）幣別一致為 USD。

---

## 修復 ④ 圖片解析度寫死 1K（填各模型實際支援尺寸）

### 根因（已知，非 bug）
`lib/config/registry.py` 所有圖片模型的 `supported_image_sizes` 目前都填 `["1K"]`（先前佔位值），
所以分鏡 / 設定頁的圖片解析度選擇器只有單一選項 → 顯示為唯讀。

### 待辦（需資料）
查各圖片模型實際支援的尺寸，填進 registry。**此項需先取得各模型官方文件的支援尺寸清單**，
執行 AI 不應臆造數值。處理方式：
1. 對 registry 內每個 `media_type="image"` 的模型，查其供應商文件的支援解析度/尺寸。
2. 填入該模型的 `supported_image_sizes`（例：Gemini 圖片模型若支援 1K/2K → `["1K", "2K"]`；
   某些模型支援 512/768/1024 → 用其文件用語）。
3. 確認 `supported_image_sizes` 的字串值會原樣傳給後端 `image_size` 參數並被該 backend 接受
   （檢查 `lib/image_backends/<provider>.py` 的 `generate` 如何用 image_size，避免填了 UI 能選但
   backend 不認的值）。

> 若無法取得某模型的確切支援清單，保持 `["1K"]` 不動，並在 PR 說明哪些模型待補。
> 不要為了讓選擇器「能點」而填入未經查證的尺寸。

### 驗收
- registry 載入正常：`uv run python -c "from lib.config.registry import PROVIDER_REGISTRY"`。
- `tests/test_config_registry.py` / `test_config_registry_models.py` 全綠。
- 對有填多尺寸的模型，前端圖片解析度選擇器出現多選項可切換；選後生成，
  版本面板的「尺寸」欄位顯示所選值（驗證 end-to-end）。

---

## 執行順序建議
① → ②（影片相關，相依概念接近）→ ③（幣別，獨立）→ ④（需查資料，可最後或並行）。

## 完成後
回報每項的：改了哪些檔/行、新增哪些測試、驗收結果（測試輸出）。我（Claude）會逐項驗收。
