## MODIFIED Requirements

### Requirement: ASSISTANT_PROVIDER 環境變數與 system_setting.assistant_provider 必須接受新值 openai-full

系統 SHALL 在 `_resolve_active_provider_id` 中接受 `gemini-full`、`gemini-lite`、`openai-lite`、`openai-full`、`claude` **五個**合法值。未設定或為空時 MUST fallback 到 `gemini-lite`。環境變數優先於 DB 設定。無效值 MUST 記錄 warning 並 fallback 到 `gemini-lite`。

#### Scenario: 環境變數設定 openai-full
- **WHEN** 容器啟動時 `ASSISTANT_PROVIDER=openai-full`
- **THEN** 新建會話預設使用 `openai-full` provider,session id 以 `openai-full:` 起頭

#### Scenario: 僅 DB 設定 openai-full
- **GIVEN** 環境變數未設定,`system_setting.assistant_provider = 'openai-full'`
- **WHEN** 建立新會話
- **THEN** 使用 `openai-full` provider

#### Scenario: 環境變數與 DB 同時設定,環境變數優先
- **GIVEN** `ASSISTANT_PROVIDER=openai-lite` 且 DB 設定為 `openai-full`
- **WHEN** 建立新會話
- **THEN** 使用 `openai-lite`(環境變數勝出)

#### Scenario: 無效值 fallback
- **GIVEN** `ASSISTANT_PROVIDER=garbage`
- **WHEN** 建立新會話
- **THEN** 系統 MUST 記錄 warning 並使用 `gemini-lite`

### Requirement: 前端必須以「provider × 模式」二維選擇呈現助手執行階段

前端在 `/settings` 助手區與新會話建立處 MUST 提供二維選擇器:第一維 provider(Gemini / OpenAI / Claude),第二維 模式(對話 / 工作流)。**目前可用組合擴充為五個**;`openai × full` 不再禁用。`claude × lite` 仍以禁用態顯示並附帶「未實作」提示。使用者選擇 MUST 同步映射到合法的 `provider_id`:

| Provider | 模式 | provider_id |
|---|---|---|
| Gemini | 對話 | `gemini-lite` |
| Gemini | 工作流 | `gemini-full` |
| OpenAI | 對話 | `openai-lite` |
| OpenAI | 工作流 | `openai-full`(本次新增) |
| Claude | 工作流 | `claude` |
| Claude | 對話 | (禁用) |

#### Scenario: 使用者選 OpenAI × 工作流
- **WHEN** 使用者在選擇器選 OpenAI 列與工作流模式
- **THEN** 前端把對應設定 PUT 到 `system_setting.assistant_provider = 'openai-full'`,下次新會話使用 `openai-full` provider

#### Scenario: 從原本禁用態解鎖
- **GIVEN** 使用者首次打開 settings,本變更已部署
- **THEN** OpenAI × 工作流格 MUST 顯示為可選擇態(非禁用),tooltip 顯示 capability 描述而非「未實作」

#### Scenario: 不可用組合仍禁用
- **WHEN** 使用者嘗試選 Claude × 對話
- **THEN** 該組合按鈕禁用,hover 顯示 tooltip「Claude 對話模式尚未實作」

### Requirement: lite 與 full 命名必須有清晰文案,不再使用「不支援」措辭

前端 `ASSISTANT_PROVIDER_LABELS` MUST 用「Gemini · 對話模式」/「Gemini · 工作流模式」/「OpenAI · 對話模式」/「**OpenAI · 工作流模式**」/「Claude · 工作流模式」之類的描述性標籤。當前 session 處於對話模式時,banner(若有)MUST 表述為「目前為對話模式,僅支援文字交流;切換至工作流模式可使用 AI 自動化生成劇本/分鏡等」,不得使用「不支援」「lite 限制」等用語。

#### Scenario: openai-full 標籤
- **WHEN** session capabilities `tier="full"` 且 provider=`openai-full`
- **THEN** UI 顯示「OpenAI · 工作流模式」標籤,不顯示降級 banner

#### Scenario: openai-lite 升級提示
- **WHEN** 使用者在 `openai-lite` session 中,UI 顯示 banner
- **THEN** banner MUST 提供切換到「OpenAI · 工作流模式」的可見入口(本變更前該入口指向其他 provider,本變更後指向 `openai-full`)
