## ADDED Requirements

### Requirement: ASSISTANT_PROVIDER 环境变量与 system_setting.assistant_provider 必须接受新值 gemini_full

系统 SHALL 在 `_resolve_active_provider_id` 中接受 `gemini_full`、`gemini_lite`、`openai_lite`、`claude` 四個合法值。未设置或为空时 MUST fallback 到 `gemini_lite`。环境变量优先于 DB 设定。无效值 MUST 记录 warning 并 fallback 到 `gemini_lite`。

#### Scenario: 环境变量设定 gemini_full
- **WHEN** 容器启动时 `ASSISTANT_PROVIDER=gemini_full`
- **THEN** 新建会话默认使用 `gemini-full` provider，session id 以 `gemini-full:` 起头

#### Scenario: 仅 DB 设定
- **GIVEN** 环境变量未设置，`system_setting.assistant_provider = 'gemini_full'`
- **WHEN** 创建新会话
- **THEN** 使用 `gemini-full` provider

#### Scenario: 环境变量与 DB 同时设定，环境变量优先
- **GIVEN** `ASSISTANT_PROVIDER=gemini_lite` 且 DB 设定为 `gemini_full`
- **WHEN** 创建新会话
- **THEN** 使用 `gemini-lite`（环境变量胜出）

#### Scenario: 无效值 fallback
- **GIVEN** `ASSISTANT_PROVIDER=garbage`
- **WHEN** 创建新会话
- **THEN** 系统 MUST 记录 warning 并使用 `gemini-lite`

### Requirement: capabilities 必须由后端权威下发，前端 fallback 仅用于初次渲染

后端 `_with_session_metadata` 与 `SessionMeta` MUST 在所有 SSE event、session list、session detail API 中包含 `capabilities` 字段。前端 `resolveAssistantCapabilities` MUST 优先使用 server 提供的 capabilities，仅在缺失时才使用本地 fallback；fallback MUST 是保守值（`tier="lite"`、`supports_tool_calls=false`、`supports_subagents=false`），不得硬编码 per-provider 能力表。

#### Scenario: server 携带 capabilities
- **WHEN** 前端收到 snapshot event 含 `capabilities: {tier: "full", supports_tool_calls: true, ...}`
- **THEN** UI 显示工具调用相关入口；不显示「不支援」相关 banner

#### Scenario: server 暂未携带 capabilities（首屏）
- **WHEN** session list 响应尚未返回，前端用 `inferAssistantProvider(sessionId)` 推测
- **THEN** UI 用保守 fallback（lite 能力）渲染，待 server 数据到达后立即覆盖

### Requirement: 前端必须以「provider × 模式」二维選择呈现助手运行时

前端在 `/settings` 助手区与新会话创建处 MUST 提供二维選择器：第一维 provider（Gemini / OpenAI / Claude），第二维 模式（对话 / 工作流）。当前不可用组合（OpenAI × 工作流）MUST 以禁用态显示并附带「未实现」提示。用户選择 MUST 同步映射到合法的 `provider_id`：

| Provider | 模式 | provider_id |
|---|---|---|
| Gemini | 对话 | `gemini-lite` |
| Gemini | 工作流 | `gemini-full` |
| OpenAI | 对话 | `openai-lite` |
| OpenAI | 工作流 | （禁用） |
| Claude | 工作流 | `claude` |
| Claude | 对话 | （禁用） |

#### Scenario: 用户選 Gemini × 工作流
- **WHEN** 用户在選择器選 Gemini 列与工作流模式
- **THEN** 前端把对应设定 PUT 到 `system_setting.assistant_provider = 'gemini_full'`，下次新会话使用 full provider

#### Scenario: 不可用组合禁用
- **WHEN** 用户尝试選 OpenAI × 工作流
- **THEN** 该组合按钮禁用，hover 显示 tooltip「OpenAI 工作流模式尚未实现」

### Requirement: lite 与 full 命名必须有清晰文案，不再使用「不支援」措辞

前端 `ASSISTANT_PROVIDER_LABELS` MUST 用「Gemini · 对话模式」/「Gemini · 工作流模式」/「OpenAI · 对话模式」/「Claude · 工作流模式」之类的描述性标签。当前 session 处于对话模式时，banner（若有）MUST 表述为「当前为对话模式，仅支持文字交流；切换至工作流模式可使用 AI 自动化生成剧本/分镜等」，不得使用「不支援」「lite 限制」等用语。

#### Scenario: 对话模式 banner 文案
- **WHEN** 当前 session capabilities `tier="lite"`
- **THEN** banner 文案 MUST 提及「对话模式」并提供切换到工作流模式的可见入口

#### Scenario: 工作流模式无降级 banner
- **WHEN** 当前 session capabilities `tier="full"`
- **THEN** 不显示「不支援恢复旧会话」「不支援技能快捷指令」等历史 banner

### Requirement: 切换 provider 不影响既有 session 的可读性

用户切换默认 provider 后，已存在的 session（任意 provider）MUST 能继续被列出、读取历史、查看 turn。仅「在该 session 上发新消息」MUST 路由到该 session 原 provider，与默认设定无关。

#### Scenario: 旧 lite session 在 full 默认下仍可读
- **GIVEN** 用户原有 `gemini:abc...` lite session，已切换默认到 `gemini_full`
- **WHEN** 打开旧 session
- **THEN** session 历史可读、可发新消息（仍走 lite provider，因为 session id 前缀决定路由）；新建会话才走 full
