# Veo 3.1 參數能力與防呆整理

**狀態：Draft**
**最後更新：2026-05-26**

> 本文件整理 Veo 3.1 秒數、解析度與參考圖限制，並對照目前 repo 的實作狀態。依專案規則，尚未經使用者確認前不標記為 Done。

## 目標

讓 ArcReel 在使用 Google Veo 3.1 系列模型時，做到以下三件事：

- metadata 能反映模型真實能力。
- 前端只顯示合法選項，並在切換解析度或參考圖狀態時自動修正秒數。
- 後端收到不合法組合時能自動 coerce 或回傳可讀錯誤，避免 SDK stack trace 直接浮出。

## 官方能力基準

來源：

- Google AI for Developers: `https://ai.google.dev/gemini-api/docs/video?hl=zh-tw`
- Google Cloud Vertex AI: `https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/veo/3-1-generate`

| 模型 | provider / model id | duration | resolution | 強制條件 |
| --- | --- | --- | --- | --- |
| Veo 3.1 | `gemini-aistudio/veo-3.1-generate-preview` | 4, 6, 8 | 720p, 1080p, 4k | 1080p、4k、reference image、video extension 必須 8 秒；video extension 僅 720p |
| Veo 3.1 Fast | `gemini-aistudio/veo-3.1-fast-generate-preview` | 4, 6, 8 | 720p, 1080p, 4k | 同上 |
| Veo 3.1 Lite | `gemini-aistudio/veo-3.1-lite-generate-preview` | 4, 6, 8 | 720p, 1080p | 1080p 或 reference image 必須 8 秒；無 4k |
| Veo 3.1 | `gemini-vertex/veo-3.1-generate-001` | 4, 6, 8 | 720p, 1080p, 4k | 1080p、4k、reference image、video extension 必須 8 秒；video extension 僅 720p |
| Veo 3.1 Fast | `gemini-vertex/veo-3.1-fast-generate-001` | 4, 6, 8 | 720p, 1080p, 4k | 同上 |

注意：Vertex AI 文件目前標示 `veo-3.1-generate-preview` 與 `veo-3.1-fast-generate-preview` 已在 2026-04-02 停用，建議遷移到 `-001`；Gemini API 文件仍列出 preview IDs。ArcReel 目前維持 provider 分流：AI Studio 使用 preview ID，Vertex 使用 `-001`。

## 目前實作狀態

### 已完成

- `lib/config/registry.py`
  - `ModelInfo` 已新增 `supported_resolutions` 與 `reference_image_force_duration`。
  - `gemini-aistudio` 三個 Veo 3.1 preview 模型已補齊 duration、resolution、duration-resolution constraint 與 reference image 強制 8 秒。
  - `gemini-vertex` 的 `veo-3.1-generate-001` 與 `veo-3.1-fast-generate-001` 已補齊相同規則。

- `server/routers/providers.py` 與 `frontend/src/types/provider.ts`
  - Provider API response 已暴露 `supported_resolutions` 與 `reference_image_force_duration`。
  - 前端 `ModelInfoResponse` 型別已同步。

- `lib/video_backends/gemini.py`
  - 已加入 `_resolve_request()`、`_resolve_duration()`、`_resolve_resolution()`。
  - 解析度會先 coerce，再用 coerce 後的解析度計算秒數。
  - Lite + 4k 會降到 1080p；1080p / 4k / reference image 會強制 8 秒。
  - SDK 400 類錯誤會包成 `VeoInvalidCombinationError`，detail 含 `code=veo_invalid_combination`、message、model、hint。

- `lib/video_backends/base.py`、`lib/media_generator.py`、`server/services/generation_tasks.py`
  - `VideoGenerationResult.adjusted` 已新增。
  - `MediaGenerator` 會把調整結果寫進 version metadata。
  - `execute_video_task()` 會把 latest version 的 `adjusted` 帶回 task result。

- 前端 hooks 與工具函式
  - `frontend/src/hooks/useVideoResolutionOptions.ts` 已新增。
  - `frontend/src/hooks/useVideoDurationOptions.ts` 已支援 `currentResolution` 與 `hasReferenceImage`。
  - `frontend/src/utils/provider-models.ts` 已新增 `lookupSupportedResolutions()`、`lookupVideoModelInfo()`、`resolveVideoDurationOptions()`、`coerceDurationToOptions()` 等工具。

- 前端 UI
  - `ProjectSettingsPage` 的解析度選項會依模型 metadata 過濾；Lite 不會顯示 4k。
  - 切換解析度時，如果目前 default duration 不合法，會自動調整並顯示 toast。
  - `SegmentCard` 的 DurationSelector 在只剩 8 秒可用時，仍顯示 4s / 6s / 8s，但不合法選項會 disabled 並附 title。
  - 片段秒數若與當前解析度或 reference image 限制不符，會自動調整並顯示 toast。

### 尚未完成或待確認

- `server/routers/generate.py` 目前仍是入隊式 API：`POST /generate/video/{segment_id}` 會先回 `task_id`，實際 SDK 錯誤發生在 worker。也就是說，「直接打 API 違規組合即回 400 JSON」尚未實作成 route-level preflight。
- `VeoInvalidCombinationError` 目前在 backend 層可讀，但需要確認 worker failure payload / task UI 是否會完整顯示 `detail.code`、`message`、`hint`。
- Video extension 的「強制 720p」尚未在 resolver 中驗證；目前 `VideoGenerationRequest` 沒有明確 video extension input，所以這條規則仍需等 extension 流程落地後補。
- 尚未用真實 Google API key 驗證 SDK 對每個組合的實際接受度。

## 驗收清單

- [x] Lite 模型的 ResolutionSelect / 專案設定解析度選項沒有 4k。
- [x] 1080p / 4k 模式下 DurationSelect 只允許 8s，不合法選項 disabled。
- [x] 有 reference image 時 DurationSelect 只允許 8s。
- [x] 後端收到 Lite + 4k + 4s 會 coerce 成 Lite + 1080p + 8s，並記錄 `adjusted`。
- [x] Provider metadata API 會回傳 `supported_resolutions` 與 `reference_image_force_duration`。
- [x] 針對 resolver、metadata、frontend hooks、SegmentCard 的 targeted tests 通過。
- [ ] API 直接打違規組合時，route-level 回 400 JSON，而不是排隊後由 worker failed。
- [ ] worker/task failure UI 完整呈現可讀錯誤 detail。
- [ ] Video extension 後端強制 720p 規則完成。
- [x] `uv run python -m pytest` 全綠。
- [x] `cd frontend && pnpm check` 全綠。
- [x] `uv run ruff check . && uv run ruff format --check .` 全綠。
- [ ] 真實 Google API smoke test 完成。

結論：本地測試、typecheck、lint 與 format check 已通過；需求層完整驗收尚未通過，因為 route-level 400、worker/task UI 錯誤呈現、video extension 720p 強制與真實 Google API smoke test 仍未完成。

## 本輪驗證紀錄

2026-05-26 已跑 targeted tests：

```bash
uv run pytest tests/lib/video_backends/test_gemini_resolver.py tests/test_config_registry.py tests/test_media_generator_module.py
```

結果：24 passed。

```bash
pnpm exec vitest run src/hooks/useVideoDurationOptions.test.tsx src/hooks/useVideoResolutionOptions.test.tsx src/components/canvas/timeline/SegmentCard.test.tsx
```

執行位置：`frontend/`

結果：3 test files passed，14 tests passed。

2026-05-26 已跑完整本地驗收：

```bash
uv run python -m pytest
```

結果：1642 passed，4 warnings。

```bash
pnpm check
```

執行位置：`frontend/`

結果：typecheck 通過；53 test files passed，279 tests passed。

```bash
uv run ruff check .
uv run ruff format --check .
```

結果：`All checks passed!`；352 files already formatted。

## 後續建議

1. 決定錯誤回傳策略：
   - 若要符合「直接 API 回 400」，在 `server/routers/generate.py` 入隊前做 provider/model/resolution/duration preflight。
   - 若維持 async queue 語意，則把驗收條件改成「task failed payload 與 UI 顯示可讀錯誤」。

2. 補 worker 錯誤 detail 傳遞測試：
   - 建議測 `GenerationWorker` 或 task repository 的 failed payload 是否保留 structured detail。

3. 補 video extension resolver 條件：
   - 先在 `VideoGenerationRequest` 建模 extension input，再把 720p / 8s coercion 放進 `_resolve_request()`。

4. 後續若再跑全量驗收，先確認 dirty tree：
   - 目前工作樹有多個與 Veo 無直接關係的變更，例如 Ark / BytePlus rename。若全量測試失敗，要先分辨是否由本任務造成。

## 不在本文件範圍

- 每個分鏡選不同生圖或影片模型。
- Ark / BytePlus、Grok、OpenAI 的影片模型能力規則。
- 重新設計影片生成 queue 或 task 狀態模型。
