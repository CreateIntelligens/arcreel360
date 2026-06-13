## Why

目前 ArcReel 助手运行时只有两条可用路径：`claude`（绑定 Claude Code bundled CLI 与 OAuth 登录态）与 `gemini-lite` / `openai-lite`（仅纯对话，不支持工具调用、子代理与权限钩子）。结果是想用 Gemini 的用户**必须放弃工作流自动化**（生成剧本、分镜、角色、线索、视频等），因为这些 skill 全部依赖 tool-calling。Gemini API 本身完整支持 function calling、parallel tools 与 streaming，缺的只是项目内的对接层。

本变更新增一条 `gemini-full` 路径，提供与 Claude provider 同等 tier 的能力（工具循环、白名单沙盒文件 IO、子代理调度、权限闸门、流式 function call），让用户能在不绑定 Claude 的前提下完整跑通漫画/旁白工作流。同时澄清 `lite` / `full` 命名歧义：`lite` 改为「对话模式」、`full` 为「工作流模式」，前端给用户显式選择。

## What Changes

- **新增** `GeminiFullRuntimeProvider`（位于 `server/agent_runtime/`），实现 `AssistantRuntimeProvider` 协议；`capabilities.tier="full"`，`supports_tool_calls`/`supports_subagents`/`supports_resume`/`supports_permission_hooks` 全部为 `true`。
- **新增** Gemini function-calling 工具循环引擎：把项目内 7 個 skill（`manga-workflow` / `generate-script` / `generate-storyboard` / `generate-characters` / `generate-clues` / `generate-video` / `compose-video`）翻译为 Gemini `FunctionDeclaration`，按 `functionCall → tool 执行 → functionResponse` 反复迭代直到模型给出纯文本终态。
- **新增** 白名单沙盒文件 IO 工具（`fs_read` / `fs_write` / `fs_list` / `run_subagent`）。允许的根目录限定为 `projects/{project_name}/`；允许的子路径白名单为 `source/` / `scripts/` / `characters/` / `clues/` / `storyboards/` / `videos/` / `drafts/` / `output/` / `project.json`。任何越界访问 SHALL 被工具层在执行前拒绝并返回结构化错误。
- **新增** 流式 function call、parallel tool call、PreToolUse 风格的权限闸门钩子；权限被拒时 SHALL 把 deny 原因塞回 `functionResponse` 让模型自己决定下一步。
- **修改** session 持久化复用現有 `agent_messages` 表（无需额外迁移），但 message payload 新增 `tool_use` / `tool_result` / `permission_decision` 三种 type，projector 与前端 turn grouper 须能呈现工具调用块。
- **修改** assistant runtime 選择逻辑：`ASSISTANT_PROVIDER` 与 DB `assistant_provider` 设定接受新值 `gemini_full`；前端在 `/settings` 与新会话创建处，把現有「provider」单選改为「provider × mode」二维選择（Gemini × 对话/工作流、OpenAI × 对话、Claude × 工作流）。
- **修改** 前端 `ASSISTANT_PROVIDER_LABELS` 与 banner 文案：明确 `lite=对话模式`、`full=工作流模式`，移除「lite 不支持」这种含糊措辞。
- **BREAKING** 无对外 API 破坏。`gemini-lite` 与 `openai-lite` 的現有 session 行为与对外契约保持不变。

## Capabilities

### New Capabilities

- `gemini-full-runtime`：定义 GeminiFullRuntimeProvider 的对外契约——capabilities 等级、Gemini function-calling 工具循环、流式行为、session 持久化与 lite provider 共用 `agent_messages` 表的兼容性、与 `gemini-lite` 的切换边界。
- `assistant-tool-sandbox`：定义助手工具执行环境的白名单沙盒规则——可访问根目录、白名单子目录清单、越界拒绝行为、PreToolUse 权限闸门协议、`fs_read`/`fs_write`/`fs_list`/`run_subagent` 四個工具的输入输出契约。本 capability 设计为 provider-agnostic：未来若新增其他 full-tier provider（如 OpenAI Assistants v2、Claude 直连 API）可复用同一沙盒规格。
- `assistant-runtime-selection`：定义用户在多 provider × 多模式之间的選择契约——`ASSISTANT_PROVIDER` 环境变量与 `assistant_provider` 系统设定的合法值、前端選择器 UI 行为、capabilities 由后端 SSE event 注入并被前端 `resolveAssistantCapabilities` 消费的数据流、`lite` / `full` 命名语义。

### Modified Capabilities

无。`workflow-orchestration` 現有规格本身就是 provider-agnostic 的（要求 manga-workflow skill 检测项目状态并 dispatch 对应 subagent，不限定 LLM 来源），新 provider 只要忠实实现 skill 协议即可，无需修改 spec-level requirements。

## Impact

**新增模块**
- `server/agent_runtime/gemini_full_runtime_provider.py`（主 provider 实现）
- `server/agent_runtime/tool_sandbox.py`（白名单沙盒 + fs 工具）
- `server/agent_runtime/skill_function_declarations.py`（skill → Gemini FunctionDeclaration 翻译）
- `server/agent_runtime/permission_gate.py`（PreToolUse 风格闸门）

**修改模块**
- `server/agent_runtime/service.py`：`runtime_provider_registry` 注册新 provider；`_resolve_active_provider_id` 支持 `gemini_full` 值。
- `server/agent_runtime/session_identity.py`：新增 `GEMINI_FULL_PROVIDER_ID` 与 `gemini-full:` session id 前缀；`infer_provider_id` 支持新前缀。
- `server/agent_runtime/turn_grouper.py` / `stream_projector.py`：新增 `tool_use` / `tool_result` content block 处理。
- `server/agent_runtime/text_backend_runtime_provider.py`：注释更新（lite 不再代表「能力受限」，而是「对话模式」）。
- `frontend/src/types/assistant.ts`：`ASSISTANT_PROVIDER_LABELS` 增加 `gemini-full`；`inferAssistantProvider` 支持 `gemini-full:` 前缀。
- `frontend/src/components/copilot/AgentCopilot.tsx`：banner 文案改为「对话模式 vs 工作流模式」表述。
- `frontend/src/components/SettingsPage`（或对应 settings UI）：provider × mode 選择器。

**依赖**
- 后端：`google-genai`（已用于 lib/gemini_shared/）—— 复用，无需新增。需要确认現有版本支持 streaming function call；不支持时升级到对应版本。
- 前端：无新依赖。

**数据库**
- `agent_messages` 表：无 schema 变更。payload JSON 内新增 `tool_use` / `tool_result` / `permission_decision` 三种 type，向前兼容（旧 lite session 不含这些 type）。

**外部 API**
- 公开 HTTP API 无破坏。`/api/v1/projects/{name}/assistant/sessions/send` 与 `/.../stream` 的请求/响应 schema 不变；新 provider 只是把对应字段（`provider`、`capabilities`、turn 结构）填上对应值。

**风险**
- **skill prompt 移植成本**：現有 SKILL.md 是给 Claude 看的，Gemini 解读同样 prompt 的行为可能不同，需逐 skill 实测调整。第一阶段先接 1-2 個简单 skill（`generate-script` / `generate-characters`）验证路径，通过后再扩展。
- **沙盒覆盖完整性**：白名单需在工具层与编排层双重校验。仅靠白名单不够时（如模型试图通过 `..` 或符号链接绕过），须在路径解析后做 `Path.resolve().is_relative_to(allowed_root)` 检查。
- **运行时性能**：tool-call loop 每轮要往返 Gemini API，长链工作流可能比 Claude SDK 慢。可在文档中提示用户工作流模式延迟较高。
