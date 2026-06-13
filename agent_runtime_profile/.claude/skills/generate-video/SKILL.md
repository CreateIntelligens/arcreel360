---
name: generate-video
description: 為劇本場景生成影片片段。當使用者說"生成影片"、"把分鏡圖變成影片"、想生成某個場景的影片、或影片生成中斷需要續傳時使用。支援整集批次、單場景、斷點續傳等模式。
---

# 生成影片

使用 Veo 3.1 API 為每個場景/片段建立影片，以分鏡圖作為起始幀。

> 畫面比例、時長等規格由專案配置和影片模型能力決定，指令碼自動處理。

## 命令列用法

```bash
# 標準模式：生成整集所有待處理場景（推薦）
python .claude/skills/generate-video/scripts/generate_video.py episode_{N}.json --episode {N}

# 斷點續傳：從上次中斷處繼續
python .claude/skills/generate-video/scripts/generate_video.py episode_{N}.json --episode {N} --resume

# 單場景：測試或生成
python .claude/skills/generate-video/scripts/generate_video.py episode_{N}.json --scene E1S1

# 批次自選：指定多個場景
python .claude/skills/generate-video/scripts/generate_video.py episode_{N}.json --scenes E1S01,E1S05,E1S10

# 全部待處理
python .claude/skills/generate-video/scripts/generate_video.py episode_{N}.json --all
```

> 所有任務一次性提交到生成佇列，由 Worker 按 per-provider 併發配置自動排程。

## 工作流程

1. **載入專案和劇本** — 確認所有場景都有 `storyboard_image`
2. **生成影片** — 指令碼自動構建 Prompt、呼叫 API、儲存 checkpoint
3. **稽核檢查點** — 展示結果，使用者可生成不滿意的場景
4. **更新劇本** — 自動更新 `video_clip` 路徑和場景狀態

## Prompt 構建

Prompt 由指令碼內部自動構建，根據 content_mode 選擇不同策略。指令碼從劇本 JSON 讀取以下欄位：

**image_prompt**（用於分鏡圖參考）：scene、composition（shot_type、lighting、ambiance）

**video_prompt**（用於影片生成）：action、camera_motion、ambiance_audio、dialogue、narration（僅 drama）

- 說書模式：`novel_text` 不參與影片生成（後期人工配音），`dialogue` 僅包含原文中的角色對話
- 劇集動畫模式：包含完整的對話、旁白、音效
- Negative prompt 自動排除 BGM

## 生成前檢查

- [ ] 所有場景都有已批准的分鏡圖
- [ ] 對話文字長度適當
- [ ] 動作描述清晰簡單
