# 內容模式參考

透過 `project.json` 的 `content_mode` 欄位切換。各 skill 的指令碼會自動讀取並應用對應規格，無需在 prompt 中指定畫面比例。

| 維度 | 說書+畫面（narration，預設） | 劇集動畫（drama） |
|------|---------------------------|-----------------|
| 資料結構 | `segments` 陣列 | `scenes` 陣列 |
| 畫面比例 | 專案配置（預設 9:16 豎屏） | 專案配置（預設 16:9 橫屏） |
| 預設時長 | 專案配置（預設 4 秒/片段） | 專案配置（預設 8 秒/場景） |
| 時長可選 | 由影片模型能力決定 | 由影片模型能力決定 |
| 對白來源 | 後期人工配音（小說原文） | 演員對話 |
| 影片 Prompt | 僅角色對話（如有），無旁白 | 包含對話、旁白、音效 |
| 預處理 Agent | split-narration-segments | normalize-drama-script |

## 影片規格

- **解析度**：圖片 1K，影片 1080p
- **生成方式**：每個片段/場景獨立生成，分鏡圖作為起始幀
- **拼接方式**：ffmpeg 拼接獨立片段，不使用 Veo extend 串聯鏡頭
- **BGM**：透過 `negative_prompt` API 引數自動排除，後期用 compose-video 新增

## Veo 3.1 extend 說明

- 僅用於延長**單個**片段/場景（每次 +7 秒，最多 148 秒）
- **僅支援 720p**，1080p 無法延長
- 不適合串聯不同鏡頭

## Prompt 語言

- 圖片/影片生成 prompt 使用**繁體中文**；JSON 鍵名與模型列舉值可用英文。
- 採用敘事式描述，不使用關鍵詞羅列。
- （Python 側真相源：`lib/prompt_language.py` 的 `PROMPT_LANGUAGE_RULE`。新增生成入口時請引用該常數，勿自寫一份。）

> 參考 `docs/google-genai-docs/nano-banana.md` 第 365 行起的 Prompting guide and strategies。
