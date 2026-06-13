## Context

ArcReel 助手运行时（assistant runtime）当前由 `server/agent_runtime/service.py` 注册三条 provider：

| Provider | 实现 | tier | 工具调用 |
|---|---|---|---|
| `claude` | `ClaudeRuntimeProvider`（薄封装 `ClaudeSDKClient`） | full | ✅（由 SDK 内部跑工具循环） |
| `gemini-lite` | `GeminiLiteProvider`（继承 `BaseTextBackendRuntimeProvider`） | lite | ❌ |
| `openai-lite` | `OpenAILiteProvider`（同上） | lite | ❌ |

工作流编排逻辑（拆集、生成剧本、生成分镜等）由 `agent_runtime_profile/.claude/skills/` 下的 7 個 skill 提供，全部以 SKILL.md + tool 调用契约的形式定义。Claude provider 通过 `ClaudeSDKClient` 自动加载这些 skill 并跑工具循环；lite provider 完全不实现 tool calling，只能纯对话。

用户切换到 `gemini-lite` 后，对话能用，但工作流功能（角色生成、剧本生成、分镜生成等）全部失效——按钮 / 入口要么消失，要么返回 `UnsupportedCapabilityError`。

Gemini API（`google-genai` SDK，已用于 `lib/gemini_shared/`）原生支持 function calling、parallel tools 与 streaming。本设计的核心问题不是「Gemini 能不能做工作流」，而是「ArcReel 怎么把已有的 skill 协议翻译为 Gemini function declarations，并实现一個等同 Claude SDK 内部行为的工具循环 + 沙盒」。

约束：
- 后端代码与前端构建产物均走 docker compose volume 挂载，不嵌入镜像。新增模块须遵循同样模式。
- session 持久化已落到 PostgreSQL `agent_messages` 表（`lib/db/models/agent_message.py`），新 provider 必须复用。
- capabilities 通过 SSE event 注入由前端 `resolveAssistantCapabilities` 消费，已自动同步——无需另外打通配置通道。

## Goals / Non-Goals

**Goals:**
- 让用户可在不安装/不登录 Claude Code CLI 的前提下，使用 Gemini API 跑通完整工作流（角色 / 线索 / 剧本 / 分镜 / 视频生成与合成）。
- 工具调用层与 provider 解耦：白名单沙盒 + skill function declarations 作为可复用模块，未来接 OpenAI Assistants v2 / Claude HTTP API 时可重用。
- session 持久化、SSE event 协议、turn grouper 行为对前端透明：現有 UI 在 `gemini-full` session 下表现一致，仅 capabilities 注入不同。
- 提供清晰的 provider × 模式選择 UX：把 `lite` / `full` 命名歧义解决在 UI 层。

**Non-Goals:**
- 不实现「Claude SDK 等价物」的全套 SDK feature——仅覆盖 ArcReel 实际用到的 skill / tool 子集。
- 不重写現有 7 個 skill 的 SKILL.md 行为契约；本变更只做协议翻译，skill 内部步骤保持不变。
- 不引入第二条文件 IO 路径（如 git worktree、远程文件系统）；沙盒只覆盖本地 `projects/` 目录。
- 不在 Gemini provider 上实现 Claude SDK 特有的「subagent in fresh context」隔离——退化为同 session 串行 dispatch（够用，未来可扩展）。
- 不重写 `gemini-lite`：保留作为「快速对话」選項，与 `gemini-full` 共存。

## Decisions

### 决策 1：用 Gemini 原生 function calling 而非自研 prompt-based tool 协议

**選择**：用 `google-genai` SDK 的 `Tool(function_declarations=[...])` 接口，让模型直接吐 `functionCall` 结构化输出。

**替代方案**：在 system prompt 里教模型用特定格式（如 `<tool>name</tool><args>...</args>`）输出工具调用，然后用正则/JSON 解析。这是 LangChain ReAct 等框架的早期做法。

**理由**：原生 function calling 由 Gemini 服务端 grammar-constrained decoding 保证 JSON 合法性，无解析失敗回退，也支持 parallel calls 与 streaming。Prompt-based 协议遇到长 args 时容易截断、JSON 半截、引号转义错。Gemini 1.5+ / 2.x / 3.x 全家族都支持原生 function calling，已稳定 18+ 個月。

### 决策 2：白名单沙盒采用「正路径 + 实路径」双重校验

**選择**：每次工具调用先把请求路径用 `Path(request).resolve()` 解析为绝对路径，再用 `is_relative_to(project_root / project_name)` 校验，且第一段必须落在白名单子目录之一（`source/` / `scripts/` / `characters/` / `clues/` / `storyboards/` / `videos/` / `drafts/` / `output/` / `project.json`）。

**替代方案**：（a）只做字符串前缀匹配；（b）依赖 OS chroot；（c）开放整個 `projects/{name}/` 不限子目录。

**理由**：
- 字符串匹配会被 `..` / 符号链接绕过。
- chroot 在容器里需要额外特权与挂载隔离，复杂度过高。
- 不限子目录会让模型有机会写到 `projects/{name}/.arcreel.db` 或 `.agent_data/` 这类 runtime 内部文件，破坏数据完整性。
- 双重校验在 Python 标准库可纯路径运算完成，零依赖、零特权、可单元测试。

### 决策 3：工具循环跑在 provider 内部 asyncio task，不复用 ClaudeSessionManager

**選择**：仿照 `BaseTextBackendRuntimeProvider._run_generation` 的 task 模式，在 `GeminiFullRuntimeProvider` 中实现 `_run_workflow_loop`：每轮调一次 `generate_content_stream` 拿到 functionCall，本地执行工具，把 functionResponse 喂回，循环直至模型回纯文本或主动 stop。message_buffer 与 SSE 流推送沿用現有协议。

**替代方案**：抽象出统一的 `ToolLoopRunner` 让 Claude 与 Gemini 都用。

**理由**：Claude SDK 内部已有自己的工具循环；强行抽象统一接口要么破坏 SDK 封装、要么变成只服务 Gemini 的伪抽象。短期内只有 Gemini 一個 full-tier 自研 provider，先把它做扎实，未来出现第二個再提取共性。

### 决策 4：skill function declarations 由代码生成，不放进数据库

**選择**：在 `server/agent_runtime/skill_function_declarations.py` 里把 7 個 skill 的输入参数表手写为 `FunctionDeclaration` 常量。每個 skill 一個函数，封装 `FunctionDeclaration(name=..., description=..., parameters=...)` 与「执行该 skill 时如何调用現有 service / pm / project_manager」的胶水代码。

**替代方案**：解析 SKILL.md 的 frontmatter 自动生成。

**理由**：SKILL.md 的描述是给 LLM 看的自然语言，不是结构化 schema；自动解析需要先定义 frontmatter schema，再写解析器，再处理边界情况——成本远高于 7 份手写常量。手写还可针对 Gemini 调整 description 措辞，提升触发准确率。未来 skill 增多时可重新评估自动化。

### 决策 5：权限闸门以「拒绝时把 deny 原因塞回 functionResponse」为默认

**選择**：当用户拒绝一次工具调用时，不抛异常中断对话；而是构造一個 `functionResponse(name=<tool>, response={"error": "permission denied", "reason": "..."})` 喂回模型，让模型自己判断是要换路、放弃还是询问用户。

**替代方案**：抛异常中断 → 让用户重新发消息。

**理由**：Claude SDK 的 PreToolUse hook 行为模式如此（permission deny 也是模型可见的 tool result，不是 transport-level 错误）。模型若知道为何被拒，能自适应（例如换文件名、退而求其次只读不写）；若直接中断则破坏对话流，且模型的「想做什么」上下文丢失。

### 决策 6：lite/full 命名通过「前端文案 + provider id」双管齐下

**選择**：保留 `gemini-lite` / `gemini-full` 两条 provider id（向后兼容已存在的 lite session）；前端 `ASSISTANT_PROVIDER_LABELS` 改为 `Gemini · 对话模式` / `Gemini · 工作流模式`，banner 文案不再说「不支持」，改为「当前为对话模式，仅可文字交流；切换至工作流模式可使用 AI 自动化生成剧本/分镜等」。

**替代方案**：完全废弃 `gemini-lite` 并入 `gemini-full`，工作流能力按运行时探测开关。

**理由**：lite 的对话延迟比 full 低（不需要 tool roundtrip），快速问答場景仍有价值；保留两条 id 并提供清晰文案，让用户按需選择。已有 `gemini:` 前缀的 session 能继续工作，无 migration。

### 决策 7：前端 UI 为「provider × 模式」二维選择

**選择**：在 `/settings` 助手区与新会话创建处，把現有 provider 单選改为：第一列選 provider（Gemini / OpenAI / Claude），第二列選模式（对话 / 工作流）；不可用组合（OpenAI × 工作流，因为本变更不实现 OpenAI full）以禁用态显示并提示「未实现」。

**替代方案**：单一下拉框列出所有组合（Gemini · 对话 / Gemini · 工作流 / OpenAI · 对话 / Claude · 工作流）。

**理由**：二维選择能让用户清楚「Gemini 可以做对话也可以做工作流」，未来接其他 provider 时只增加一列即可，UX 一致性高。

## Risks / Trade-offs

- **[Risk] skill prompt 在 Gemini 上行为偏移**：現有 SKILL.md 措辞针对 Claude，Gemini 可能解读不同（例如 Gemini 较少主动调用工具、更倾向直接回答）。**Mitigation**：第一阶段只接 `generate-script` 与 `generate-characters` 两個 skill，逐句对比 Claude/Gemini 输出做迁移测试；如发现 prompt 漂移，在 `skill_function_declarations.py` 的 description 字段加 Gemini 专属增强提示，不动 SKILL.md 本体。
- **[Risk] 工作流模式延迟显著高于 Claude SDK**：Claude SDK 用的是 long-running streaming session，连续 tool 调用时连接复用；Gemini function calling 每轮 `generateContent` 是独立请求。3-5 轮 tool 调用的工作流可能比 Claude 多 2-4 秒。**Mitigation**：UI 在工作流模式下显示明确进度提示（"调用 generate-script ..."），让等待感可见；后端确保用 `generate_content_stream` 而非 `generate_content`，至少首字 token 是 streaming 的。
- **[Risk] 沙盒被符号链接绕过**：用户或先前 session 在 `projects/{name}/source/` 里创建了符号链接指向 `/etc/passwd`，模型 `fs_read` 时是否会跨界。**Mitigation**：`Path.resolve(strict=True)` 在符号链接解析后做 `is_relative_to(project_root)` 检查，链接指向白名单外则拒绝。增加单测覆盖此場景。
- **[Risk] `agent_messages` payload schema 漂移**：新增 `tool_use` / `tool_result` 等 type 后，旧的 `gemini-lite` session 反查 history 时遇到 unknown type。**Mitigation**：`turn_grouper` 与 `stream_projector` 对未知 type 默认 pass-through 不报错；前端 turn 渲染对未实现的 content block 显示通用 "工具调用" 占位符；旧 lite session 不会包含这些 type 因此不受影响。
- **[Trade-off] subagent 隔离弱化**：原 Claude SDK 的 subagent 在独立 context 跑，避免主对话被淹没；Gemini 实现退化为「同 context 多轮 tool call」，长工作流可能撑大 context。**接受这個 trade-off**，非首期目标；未来可在 Gemini 端模拟 subagent 隔离（开新 session、回收摘要）。
- **[Trade-off] permission gate 默认 allow**：首版无前端 UI 让用户实时审批工具调用；权限闸门接口预留但默认放行，未来可挂前端 modal 做人工审批。**接受**：避免工作流被频繁阻塞，先跑通主路径再加审批 UX。

## Migration Plan

1. **代码部署**：新增 4 個后端模块（provider / sandbox / declarations / permission gate），修改 `service.py` 注册 + `session_identity.py` 前缀。docker compose 重启 arcreel 容器即可生效（代码挂载）。
2. **前端构建**：`docker compose run --rm frontend-builder` 生成 dist。
3. **数据库**：无 schema 变更，无需 alembic migration。
4. **配置**：用户在 `.env` 设 `ASSISTANT_PROVIDER=gemini_full`，或 DB `system_setting.assistant_provider='gemini_full'`，或前端 `/settings` 新選择器選「Gemini · 工作流模式」。
5. **回滚策略**：把 `ASSISTANT_PROVIDER` 改回 `gemini_lite` 或 `claude` 即可；旧 session 在新 provider id 切换时不可继续（受 `gemini-full:` 前缀限制），但能在原 provider 下继续访问。

## Open Questions

- **Q1**：parallel tool call 是否首期支持？Gemini 同一轮可能返回多個 functionCall，是串行执行还是并发？协作者评估：**首期建议串行执行**，简化错误处理，性能差距在 ArcReel 場景里不显著。
- **Q2**：`run_subagent` 工具的契约——是同步阻塞返回完整结果，还是異步返回 task_id 让模型轮询？**首期建议同步阻塞**（与 `manga-workflow` skill 現有协议一致），避免引入 task 状态机。
- **Q3**：`fs_write` 是否需要做内容审查（例如禁止写入超大文件、禁止包含特定模式）？**首期不做**，仅限制路径白名单与单文件大小（如 10 MB）。
- **Q4**：`gemini-full` session 的「可中断」语义——用户点中断后，正在跑的 tool call 是否要等执行完？**首期建议**：tool call 内部不可中断（执行原子完成），但中断信号会阻止下一轮 generate_content_stream 启动。
