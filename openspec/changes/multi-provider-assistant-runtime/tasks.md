## 1. Runtime 抽象

- [x] 1.1 审计 `AssistantService`、`SessionManager`、Claude SDK transcript 相关代码，梳理必须抽象出的 provider contract
- [x] 1.2 设计并实现 `AssistantRuntimeProvider` 接口与统一 capability 数据结构
- [x] 1.3 将現有 Claude runtime 包装为 `ClaudeRuntimeProvider`，确保現有功能在抽象层下仍可工作

## 2. Lite Provider 实现

- [x] 2.1 定义 Gemini-lite 与 OpenAI-lite 的首期能力边界：消息类型、工具范围、会话持久化策略、错误模型
- [x] 2.2 复用現有 Gemini 文本 / 多模态能力实现 `GeminiLiteProvider` 的基础对话能力
- [x] 2.3 复用現有 OpenAI 兼容能力实现 `OpenAILiteProvider` 的基础对话能力
- [x] 2.4 为 Gemini-lite 与 OpenAI-lite 增加统一流式事件输出，保证前端可以复用現有 assistant 面板
- [x] 2.5 实现 provider-specific 降级错误：如 `resume_not_supported`、`subagent_not_supported`

## 3. API 与数据模型

- [x] 3.1 调整 assistant/chat 相关路由，按 active provider 路由请求
- [x] 3.2 调整 session / snapshot / status 响应，暴露 provider 与 capability 信息
- [x] 3.3 为同步聊天端点补充 Claude / Gemini / OpenAI 的 provider 選择、能力不足与配置缺失测试覆盖

## 4. 配置与前端降级

- [x] 4.1 在系统配置中新增 assistant provider 選择与 provider 状态展示
- [x] 4.2 调整 `config-status-store` 与设置页横幅逻辑，将 Anthropic 从全局必填项改为 provider-specific requirement，并纳入 Gemini / OpenAI 配置缺失場景
- [x] 4.3 调整 assistant 面板 UI，基于 capability matrix 隐藏或禁用不支持的功能
- [x] 4.4 为 Gemini-only 与 OpenAI-only 場景补充前端测试，验证不会再因缺少 Anthropic 被误判为系统未完成

## 5. Workflow-grade 路线

- [x] 5.1 梳理 ArcReel 真正需要的 workflow-grade 能力，区分于 Claude 专属 full runtime 能力
- [x] 5.2 设计 workflow-grade provider contract：项目状态检测、分阶段推进、受限子任务执行
- [x] 5.3 评估 Gemini 与 OpenAI 哪一侧更适合作为首個 workflow-grade provider

## 6. 发布策略

- [x] 6.1 以 feature flag 或配置项方式灰度启用 Gemini-lite 与 OpenAI-lite assistant
- [x] 6.2 保留 Claude 为默认 full provider，确保現有 Anthropic 用户无行为回归
- [x] 6.3 编写迁移说明：Gemini-lite、OpenAI-lite 的支持范围、限制项，以及与 Claude full runtime 的差异