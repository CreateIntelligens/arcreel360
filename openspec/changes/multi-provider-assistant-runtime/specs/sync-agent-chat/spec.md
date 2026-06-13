## MODIFIED Requirements

### Requirement: 同步 Agent 对话端点

系统 SHALL 提供 `POST /api/v1/agent/chat` 同步端点，并根据当前激活的 assistant provider 路由请求，而不是隐式固定到 Claude runtime。

#### Scenario: active provider 为 Claude
- **WHEN** 已认证用户调用 `POST /api/v1/agent/chat`
- **THEN** 系统 SHALL 使用 Claude provider 执行对话，并保持現有 full runtime 行为

#### Scenario: active provider 为 Gemini-lite
- **WHEN** 已认证用户调用 `POST /api/v1/agent/chat`
- **THEN** 系统 SHALL 使用 Gemini-lite provider 执行对话，并返回与统一 assistant contract 对齐的回复结构

#### Scenario: active provider 为 OpenAI-lite
- **WHEN** 已认证用户调用 `POST /api/v1/agent/chat`
- **THEN** 系统 SHALL 使用 OpenAI-lite provider 执行对话，并返回与统一 assistant contract 对齐的回复结构

#### Scenario: 请求当前 provider 不支持的能力
- **WHEN** 客户端通过同步对话端点触发当前 provider 不支持的行为
- **THEN** 系统 SHALL 返回结构化的能力不足错误，而不是泄漏底层 SDK 或 provider 异常文本