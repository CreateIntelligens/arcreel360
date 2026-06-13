# 計畫：劇集成片字幕燒錄（旁白文字 → SRT → 硬燒進最終影片）

**狀態：Draft**
**目標讀者：冷啟動的執行 AI（無本對話脈絡）。照此文件即可實作，不需再自行探索架構，但需照「驗證」節確認行號未漂移。**

---

## 0. 需求與設計決策（使用者已拍板）

來源是一份「FastAPI + Whisper + Web 時間軸」的通用簡易剪映 Spec。經與 ArcReel 現況對齊後，使用者裁定兩項關鍵決策，本計畫據此大幅收斂：

1. **字幕文字來源 = 現有 segment 旁白文字，不引入 Whisper / ASR。**
   理由：ArcReel 是「小說 → 分鏡 → 逐段生成片段」，每個 segment 本就帶 `novel_text`（旁白原文）與 `duration_seconds`（時長）。字幕所需的「文字 + 時間」已內生於劇本，對成片做語音辨識是多餘的一圈。
2. **長在現有 episode 合成流程上，不另開後端 / 子系統。**
   理由：ArcReel 後端是 Python FastAPI（`server/app.py:123`），已有完整的「上傳 → 佇列 → ffmpeg 合成 → 版本控制」鏈路。原 Spec 的 Node.js/Express + fluent-ffmpeg + `/asr` + 同步 `FileResponse` 全部不採用。

**被否決的原 Spec 元素（明確不做）**：`POST /asr` 端點、Whisper API、`OPENAI_API_KEY` 環境變數需求、無歸屬的 `video_id`、HTTP 同步等待燒錄完成的 `POST /export`。

---

## 1. 現況診斷（已盤點，執行者可信賴）

### 字幕資料已齊備（無需 ASR）
- `lib/script_models.py`：
  - narration 片段：`duration_seconds: int (ge=1, le=60)`（:87）、`novel_text: str`（:89）。
  - drama 場景：`duration_seconds`（:128）、`scene_description`。
- 每段 start/end 可由「依序累加 `duration_seconds`」得出，無需偵測。

### 現有合成鏈路（複用對象）
- **合成端點**：`POST /projects/{name}/episodes/{episode}/compose`（`server/routers/project_episodes.py:539` `compose_episode_video`）→ `subprocess.run` 呼叫 skill 腳本。
- **合成腳本**：`agent_runtime_profile/.claude/skills/compose-video/scripts/compose_video.py`
  - `concatenate_simple`（:52）：`concat` demuxer + `-c copy`（**不重編碼，快**）。
  - `concatenate_with_transitions`（:78）：`filter_complex` xfade 轉場。
  - 從 `script.json` 的 `item.generated_assets.video_clip` 蒐集 `video_paths`。
  - 入口 `argparse`（:13）：`script_file` 位置參數 + `--output`。
- **成片版本控制**：已於 `2026-06-08-final-video-versioning.md` 設計，`output` 資源型別 + `VersionManager`。字幕重燒應視為「產生新一版成片」，**直接複用該版本機制**，不另造。
- **任務佇列**：`lib/generation_queue.py` `enqueue_task(task_type=...)`，現有型別 `character/clue/scene/storyboard/video`。

### 關鍵技術約束
- **燒字幕必須重新編碼**：`subtitles=` 濾鏡會改變畫面像素，與現行快速路徑的 `-c copy` 互斥。加字幕的合成必走重編碼路徑（`-c:v libx264 -c:a aac` 之類），耗時明顯高於 `concat copy`。Spec 必須讓「是否燒字幕」成為合成選項，而非無條件套用。
- **ffmpeg `subtitles=` 路徑轉義**：filter 參數內的 `:`、`\`、`'`、`[]` 需轉義；中文/含空白路徑在 Linux 容器下相對安全，但仍應用絕對路徑並對 filter 字串轉義。SRT 走獨立檔（非 inline），降低轉義風險。

---

## 2. 資料結構

### SRT 由劇本即時生成（不落庫，不新增持久欄位）
合成時讀 `script.json`，依 storyboard item 順序（與 `compose_video.py` 蒐集影片同一套順序，務必一致，否則字幕與畫面錯位）逐段：

```
start_n = Σ duration_seconds[0..n-1]
end_n   = start_n + duration_seconds[n]
text_n  = novel_text (narration) / scene_description (drama)
```

輸出標準 SRT（`HH:MM:SS,mmm`）。**時間基準取劇本 `duration_seconds`，非實際影片長度**——若實際片段長度與宣告時長有出入，未來可選擇改用 `ffprobe` 實測時長對齊（列為已知限制，見 §6）。

### 前端字幕物件（僅前端預覽用，與 SRT 對應）
沿用劇本既有欄位，不另設新 schema：
```
{ id: segment_id, start: float, end: float, text: string }
```

---

## 3. 後端變更

### 3.1 SRT 生成（新增純函式，無 I/O 副作用，好測）
新增 `lib/subtitle_srt.py`：
- `build_srt_from_script(script: dict, content_mode: str) -> str`
  - 依 §2 公式生成 SRT 字串。
  - 文字欄位空白的段落跳過（不產生空字幕條）。
  - 對 `-->` 等 SRT 保留語意無需轉義，但須處理多行 `text`（保留換行）。
- 對應單元測試 `tests/test_subtitle_srt.py`：narration / drama、空文字略過、時間累加正確、`HH:MM:SS,mmm` 格式。

### 3.2 compose 腳本支援字幕（擴充既有，不另寫路徑）
`compose_video.py`：
- 新增 CLI 旗標：`--subtitles <srt_path>`（可選）。給定時，於拼接後對輸出再跑一個 `subtitles=` 濾鏡 pass（或在 transitions 的 `filter_complex` 末端串接），並改走重編碼。
- 無 `--subtitles` 時，行為與現狀完全一致（保留 `-c copy` 快速路徑）。
- SRT 檔由呼叫端（合成端點）先用 §3.1 生成並寫入暫存路徑後傳入。

### 3.3 合成端點支援字幕選項
`server/routers/project_episodes.py` 的 `compose_episode_video`（:539）：
- 接受可選參數 `burn_subtitles: bool = False`（query 或 body）。
- 為 true 時：載入 `script.json` → `build_srt_from_script` → 寫 `drafts/episode_N/episode_N.srt`（或暫存）→ 以 `--subtitles` 傳給 compose 腳本。
- 產物仍走既有 `output` 版本控制（每次合成 = 新版），版本 metadata 增記 `burned_subtitles: true/false`，讓前端版本時光機能標示「此版含燒錄字幕」。
- **是否入 GenerationQueue**：現行 compose 端點為同步 `subprocess.run`。燒字幕重編碼更慢，建議**比照現有 video task 入 `GenerationQueue`**（`task_type="compose"` 或沿用既有合成路徑的非同步化）。若本期不改造佇列，至少確認 `subprocess` 以非阻塞方式執行（`asyncio.create_subprocess_exec` 或 `asyncio.to_thread`），避免阻塞 event loop——此為原 Spec §6.3 唯一仍適用的效能要求。

---

## 4. 前端變更（沿用現有 timeline，不引入新播放器庫除非確認）

> 原 Spec 建議 vidstack + wavesurfer。ArcReel `frontend/` 已是 React 19 + Vite，這兩個庫**技術相容可採納**，但屬於額外依賴與較大 UI 工程。本期最小範圍如下；vidstack/wavesurfer 的圖形時間軸列為 §7 後續選配。

### 4.1 最小範圍（本期）
- `FinalVideoCard`（`frontend/src/components/canvas/timeline/FinalVideoCard.tsx`）合成按鈕旁加「燒錄字幕」開關，傳 `burn_subtitles` 給 compose API。
- 字幕內容直接取自既有 segment 文字（前端已有 segment 資料），合成前可選提供「預覽 SRT」唯讀檢視。
- 版本時光機（`VersionTimeMachine.tsx`）顯示該版是否含燒錄字幕（讀 §3.3 的 metadata）。

### 4.2 選配（§7，需另行確認後再做）
- vidstack 軟字幕即時預覽（`<Track>` 餵動態 SRT/VTT blob）。
- wavesurfer 波形 + Regions 拖拉微調 segment 時間。
- 雙向時間鎖定：以**播放器為 master clock**，波形被動跟隨，避免 `timeupdate ↔ seek` 互觸發無限迴圈（原 Spec §5.1 未防此迴圈，實作時必加 `isSeeking` 旗標或單向主控）。

---

## 5. API 介面（ArcReel 風格，非原 Spec 的 /asr、/export）

### 5.1 合成（擴充既有，不新增端點）
- `POST /projects/{name}/episodes/{episode}/compose`
- 新增可選 body：`{ "burn_subtitles": false }`
- 回應沿用既有 compose 回應（成片進 `output` 版本系統）。

### 5.2 字幕預覽（可選，本期可不做）
- `GET /projects/{name}/episodes/{episode}/subtitles.srt` → `text/plain`，回 §3.1 即時生成的 SRT，供前端預覽。

**不採用**：原 Spec 的 `POST /asr`、`POST /export`（同步 FileResponse）。

---

## 6. 已知限制

1. **時間基準為宣告時長**：SRT 用劇本 `duration_seconds` 累加，若實際片段時長與宣告不符，字幕會逐段漂移。緩解：合成時以 `ffprobe` 實測每段長度對齊（後續優化）。
2. **硬字幕不可關**：燒錄後字幕焊死在畫面。若需可切換字幕，須改輸出軟字幕（`-c:s mov_text` 進 mp4 容器或外掛 VTT），本期不做。
3. **重編碼成本**：含字幕合成比 `concat copy` 慢數倍，故設為選項而非預設。

---

## 7. 後續（明確排除於本期，需再確認）
- vidstack + wavesurfer 圖形化時間軸與拖拉微調（§4.2）。
- Whisper ASR：僅在「使用者上傳**外部**影片上字幕」情境才需要，與本主線（小說生成）不同情境，需新增 audio backend + 走 ConfigService 金鑰體系後再議。
- 字幕樣式（字體/位置/描邊）自訂。

---

## 8. 驗證

1. **單元**：`uv run python -m pytest tests/test_subtitle_srt.py -v`（SRT 格式、時間累加、空段略過、narration/drama）。
2. **腳本**：對一個已生成多段影片的測試專案，手動跑 `compose_video.py <script> --output x.mp4 --subtitles y.srt`，用 `ffprobe`/播放確認字幕燒入且與畫面同步。
3. **端點**：`compose_episode_video` 帶 `burn_subtitles=true`，確認成片含字幕、進 `output` 版本系統、metadata 記錄正確；`burn_subtitles=false` 行為與現狀一致（仍走快速 copy 路徑）。
4. **回歸**：既有 compose 測試（`tests/test_projects_router.py` 等 final-video 相關）全綠，不重編碼路徑未受影響。
5. **前端**：`cd frontend && pnpm check`。
