---
name: compose-video
description: 影片後期處理與合成。當使用者說"加背景音樂"、"合併影片"、"加片頭片尾"、想為成片新增 BGM、或需要將多集影片拼接時使用。
---

# 合成影片

使用 ffmpeg 進行影片後期處理和多片段合成。

## 使用場景

### 1. 新增背景音樂

```bash
python .claude/skills/compose-video/scripts/compose_video.py --episode {N} --music background_music.mp3 --music-volume 0.3
```

### 2. 合併多集影片

```bash
python .claude/skills/compose-video/scripts/compose_video.py --merge-episodes 1 2 3 --output final_movie.mp4
```

### 3. 新增片頭片尾

```bash
python .claude/skills/compose-video/scripts/compose_video.py --episode {N} --intro intro.mp4 --outro outro.mp4
```

### 4. 後備拼接

正常流程中影片由 Veo 3.1 逐場景獨立生成，最終需要拼接成完整劇集。當標準的轉場拼接（xfade 濾鏡）因編碼引數不一致而失敗時，後備模式使用 ffmpeg concat demuxer 做無轉場的快速拼接，確保至少能輸出完整影片：

```bash
python .claude/skills/compose-video/scripts/compose_video.py --episode {N} --fallback-mode
```

## 工作流程

1. **載入專案和劇本** — 檢查影片檔案是否存在
2. **選擇處理模式** — 新增 BGM / 合併多集 / 新增片頭片尾 / 後備拼接
3. **執行處理** — 使用 ffmpeg 處理，保持原始影片不變，輸出到 `output/`

## 轉場型別（後備模式）

根據劇本中的 `transition_to_next` 欄位：

| 型別 | ffmpeg 濾鏡 |
|------|-------------|
| cut | 直接拼接 |
| fade | `xfade=transition=fade:duration=0.5` |
| dissolve | `xfade=transition=dissolve:duration=0.5` |
| wipe | `xfade=transition=wipeleft:duration=0.5` |

## 處理前檢查

- [ ] 場景影片存在且可播放
- [ ] 影片解析度一致（由 content_mode 決定畫面比例）
- [ ] 背景音樂 / 片頭片尾檔案存在（如需要）
- [ ] ffmpeg 已安裝並在 PATH 中
