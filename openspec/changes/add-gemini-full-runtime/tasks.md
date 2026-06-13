## 1. 沙盒与工具基础（先做，无 Gemini 依赖，可独立测试）

- [x] 1.1 新建 `server/agent_runtime/tool_sandbox.py`，实现 `ToolSandbox` 类：构造时接收 `project_root: Path` 与 `project_name: str`；提供 `validate_path(req_path) -> Path`，做白名单 + `is_relative_to` 双重校验；越界抛 `SandboxViolationError`
- [x] 1.2 在 `tool_sandbox.py` 中实现四個工具函数：`fs_read(sandbox, path, max_bytes=1MiB)`、`fs_write(sandbox, path, content, mode)`、`fs_list(sandbox, path)`、其中所有路径访问 MUST 经 `validate_path`
- [x] 1.3 新建 `tests/test_tool_sandbox.py`，覆盖：白名单合法访问、越界路径拒绝（含 `..` 与符号链接）、`fs_read` 截断、`fs_write` create 冲突、`fs_list` 隐藏文件过滤、单文件 10 MiB 限制
- [x] 1.4 新建 `server/agent_runtime/permission_gate.py`，实现 `PermissionGate` 协议（`check(tool_name, args, session_id) -> Allow | Deny | AskUser`）与默认放行实现 `AlwaysAllowGate`
- [x] 1.5 新建 `tests/test_permission_gate.py`，覆盖默认放行、自定义实现可挂载、Deny 时返回原因结构

## 2. Skill function declarations（手写 7 個 skill 的 schema）

- [x] 2.1 新建 `server/agent_runtime/skill_function_declarations.py`，定义 `FunctionDeclaration` 常量列表与 `SKILL_HANDLERS: dict[str, Callable]` 注册表
- [x] 2.2 翻译 `manga-workflow` skill：实作为 `manga_workflow_status` 只读编排状态查询（替代 dispatch，避免与下方 generate_* 重复）；按阶段 1-8 规则返回 next_action
- [x] 2.3 翻译 `generate-script` skill：handler 调用 `ScriptGenerator.create()` 異步生成 `scripts/episode_{N}.json`
- [x] 2.4 翻译 `generate-characters` skill：handler 调用 `ProjectManager.add_project_character`，支持批量 + skipped 报告
- [x] 2.5 翻译 `generate-clues` skill：handler 调用 `ProjectManager.add_clue`，dedup 已存在的 clue
- [x] 2.6 `generate_storyboard` skill：handler 读取 `scripts/episode_{N}.json`，遍历 segments/scenes，按 `image_prompt` batch enqueue 走 generation queue，等所有 task 完成；支持 `scene_ids` 过滤
- [x] 2.7 `generate_video` skill：与 storyboard 同模式，task_type=video，按 `video_prompt` enqueue，等待 worker 完成
- [x] 2.8 `compose_video` skill：subprocess 呼叫 `agent_runtime_profile/.claude/skills/compose-video/scripts/compose_video.py`，cwd 设为 project_path；支持可選 `music` + `music_volume`；超时 15 分钟
- [x] 2.9 加 `run_subagent` 函数：按 skill 名 dispatch 到 SKILL_HANDLERS，做参数 dict 校验，捕获 handler 异常转结构化错误
- [x] 2.10 新建 `tests/test_skill_function_declarations.py`，22 個测试覆盖注册表完整性、4 個真实 skill 各 happy path + 校验失敗、3 個占位 skill not_implemented、unknown_skill 拒绝、handler 异常隔离

## 3. GeminiFullRuntimeProvider 主体

- [x] 3.1 在 `server/agent_runtime/session_identity.py` 增加 `GEMINI_FULL_PROVIDER_ID = "gemini-full"`；prefix dict 顺序保证 `gemini-full:` 先匹配，旧 `gemini:` lite session 路由不受影响
- [x] 3.2 新建 `server/agent_runtime/gemini_full_runtime_provider.py`，继承 `BaseTextBackendRuntimeProvider` 复用 session 生命周期；capabilities tier=full、所有 supports_* True；send_new_session 创建 `gemini-full:<uuid_hex>` session
- [x] 3.3 实现 `_run_generation` 工具循环：configure `tools=[function_declarations]`，每轮 ``aio.models.generate_content`` 拿 functionCall 列表 → 串行执行 → 拼 functionResponse 喂回；超过 max_tool_turns（默认 20）发 `result(subtype="max_turns")`
- [x] 3.4 functionCall / response 落库为 `tool_use` / `tool_result` 独立 message（带 tool_use_id 关联），通过 `_persist_message` 写 `agent_messages`
- [x] 3.5 streaming token：实现 `_stream_one_turn` + `_gemini_stream`（用 `generate_content_stream` async iterator），文本 chunk 逐個 emit `stream_event` 给前端订阅者；fake SDK 不支持时自动回退 `_gemini_generate`；2 個 streaming 单测覆盖纯文本流与 functionCall+text 混合場景
- [x] 3.6 中断：复用基类 `interrupt_session` 取消 generation_task；正在执行的工具原子完成（asyncio cancellation 在 await 边界生效），下一轮不启动
- [x] 3.7 read_history / subscribe / get_status 等 — 完全继承 `BaseTextBackendRuntimeProvider`，无需额外实现
- [x] 3.8 在 `service.py` 注册 `GeminiFullRuntimeProvider`；`_resolve_active_provider_id` 接受 `gemini_full` 值（已有逻辑：环境变量 / DB 都会透传字符串到 registry，无需修改）

## 4. Stream projector 与 turn grouper 兼容工具调用

- [x] 4.1 `turn_grouper.group_messages_into_turns` 新增 `tool_use` / `tool_result` 分支：tool_use 作为 assistant turn 的 content block（创建新 assistant turn 或附加到末尾）；tool_result 通过 `_attach_tool_result` 写回同 id 的 tool_use 内（result/is_error 字段）
- [x] 4.2 `stream_projector._GROUPABLE_TYPES` 加入 `tool_use` / `tool_result`，让 live message 走 group → patch 推送给前端
- [x] 4.3 前端 `ContentBlock` 已含 `tool_use` / `tool_result` 字段；現有 `ChatMessage` 渲染组件在 Claude session 下已能显示，gemini-full session 下行为一致（工具调用块出现在 assistant turn 内）

## 5. capabilities 与 provider × 模式選择

- [x] 5.1 后端 `_capabilities_for(provider_id)` / `_hydrate_capabilities(meta)` 已在 list/get_session 注入 capabilities，新 `gemini-full` provider 自动通过 registry 命中（无需额外修改 service）
- [x] 5.2 前端 `ASSISTANT_PROVIDER_LABELS`：4 個 provider 全部更新为「× 对话/工作流模式」描述
- [x] 5.3 前端 `inferAssistantProvider`：`gemini-full:` 前缀必须先于 `gemini:` 匹配，已正确处理
- [x] 5.4 banner 加「前往設定」按鈕（`useLocation` → `/app/settings`），lite session 一鍵跳轉切換工作流模式
- [x] 5.5 `AssistantRuntimeGrid` 二維選擇器：橫軸 Gemini/OpenAI/Claude，縱軸 對話/工作流；不可用組合顯示禁用態 + tooltip「未實現」
- [x] 5.6 `.env.example` `ASSISTANT_PROVIDER` 注释更新，列出 4 個合法值与各自语义

## 6. 端到端测试与文档

- [x] 6.1 `tests/test_gemini_full_runtime.py` 9 個测试，用 SimpleNamespace fake Gemini response：覆盖单轮 text 完成、tool loop 执行 fs_read、skill dispatch（generate_characters 写入 project.json）、max_turns 终止、permission Deny 不破坏对话流
- [x] 6.2 真实 Gemini API 联调通过：`scripts/gemini_full_smoketest.py` 在 demo 项目上让模型调用 manga_workflow_status，正确读到 stage 1 信息并生成自然回覆。同时发现并修复 Gemini 3 系列的 `thought_signature` 透传要求
- [x] 6.3 沙盒真实場景安全性已验证：让模型尝试 `fs_write("/etc/passwd", ...)`，沙盒返回 `{"error": "sandbox_violation", "reason": "path outside project root"}`，对话流不中断
- [x] 6.4 `CLAUDE.md` 「Agent Runtime」章节重写：4 個 provider 表格、核心模块说明、tool_use/tool_result 持久化、provider 切换语义
- [x] 6.5 `docs/gemini-full-runtime.md` 协作者上手指南：架构总览、当前状态、4 個真实 skill / 3 個占位 skill 表、加新 skill 步骤、修改沙盒白名单、调试 tool loop、thought_signature 注意事项、路线图

## 7. 收尾

- [x] 7.1 frontend-builder 重新构建 dist；docker compose restart arcreel；/health 200
- [x] 7.2 `scripts/gemini_full_smoketest.py` 已建立 `smoketest-gemini-full` demo 项目并跑通 manga_workflow_status + sandbox escape 双場景
- [ ] 7.3 PR 描述与协作者交接（待协作者完成 generate_storyboard/video/compose 三個占位 + UI 二维選择器后撰写）
- [ ] 7.4 `openspec validate --strict` 已通过；archive 待协作者补完后执行
