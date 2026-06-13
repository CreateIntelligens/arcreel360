# Gemini Full Runtime（工作流模式）协作者指南

## TL;DR

`gemini-full` 是一条与 `claude` 同级（`tier="full"`）的助手运行时，但底层用 Gemini API 的原生 function calling。它能让用户在不绑定 Claude Code CLI 的情况下，让 AI 自动化生成剧本、角色、线索等。

启用方式：

```bash
# 方式 A：环境变量（容器启动时读）
echo "ASSISTANT_PROVIDER=gemini-full" >> .env
docker compose restart arcreel

# 方式 B：DB 设定（运行时切换）
docker compose exec postgres psql -U arcreel -d arcreel -c \
  "INSERT INTO system_setting (key, value, updated_at) VALUES ('assistant_provider', 'gemini-full', now()) \
   ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=now();"

# 方式 C：前端设置页 → 助手 → 選择「Gemini · 工作流模式」
```

需要的前置：DB 中存在 active 的 `gemini-aistudio` credential（前端设置页 → 文字供应商可设）。

## 架构总览

```
GeminiFullRuntimeProvider  ←  继承 BaseTextBackendRuntimeProvider（复用 session lifecycle / persist / SSE）
   │
   ├─ _stream_one_turn       ─→  generate_content_stream，文本 chunk 即时 emit stream_event
   ├─ _execute_tool          ─→  permission_gate.check → dispatch_tool
   │       │
   │       ├─ fs_read / fs_write / fs_list  ─→  ToolSandbox（白名单沙盒）
   │       └─ 7 個 skill                    ─→  SKILL_HANDLERS（skill_function_declarations.py）
   │
   └─ tool_use / tool_result 落库  ─→  agent_messages 表
```

## 当前状态（截至 add-gemini-full-runtime change）

| 模块 | 状态 |
|---|---|
| `tool_sandbox.py` 白名单沙盒 + fs_read/fs_write/fs_list | ✅ 完成 + 26 测试 |
| `permission_gate.py` PreToolUse 闸门（默认放行） | ✅ 完成 + 11 测试 |
| `skill_function_declarations.py` 7 個 skill 翻译 | ✅ 7 個全部接入（4 文本 + 2 队列驱动 + 1 ffmpeg） |
| `gemini_full_runtime_provider.py` 工具循环 + streaming | ✅ 完成 + 11 测试（含真实 API 联调） |
| 前端 capabilities 注入与 banner 文案 | ✅ 基本完成；二维選择器 UX 留待优化 |
| 真实 Gemini API 联调 | ✅ 已验证 manga_workflow_status + sandbox escape |

## 真实可用的 skill

| skill | 行为 | 触发示例 |
|---|---|---|
| `manga_workflow_status` | 只读，按 project.json + 文件系统判断阶段（1-8）并返回 next_action | 「检查项目状态」「现在该做什么？」 |
| `generate_characters` | 写入 `project.json` 的 characters（不立即生成图片） | 「为我新增 3 個主角：小明、小红、阿强」 |
| `generate_clues` | 写入 `project.json` 的 clues（道具/地点） | 「新增线索：玉佩（major prop）、小酒馆（location）」 |
| `generate_script` | 调用 `ScriptGenerator.create()` 生成 `scripts/episode_{N}.json` | 「生成第 1 集剧本」（前置：drafts/episode_1/step1_*.md 存在） |

资产生成 skill（走 generation queue worker，handler 阻塞等待）：

| skill | 行为 |
|---|---|
| `generate_storyboard(episode, scene_ids?)` | 读 `scripts/episode_{N}.json`，按 `image_prompt` batch enqueue task_type=storyboard，等所有完成；可用 `scene_ids` 过滤 |
| `generate_video(episode, scene_ids?)` | 同模式，task_type=video，按 `video_prompt` enqueue |
| `compose_video(episode, music?, music_volume?)` | subprocess 跑 ffmpeg compose 脚本，超时 15 分钟，输出 `output/episode_{N}_final.mp4` |

## 如何加新 skill

1. 在 `server/agent_runtime/skill_function_declarations.py` 加 `FunctionDeclaration` 常量

   ```python
   MY_SKILL_DECL = FunctionDeclaration(
       name="my_skill",
       description="清晰描述触发場景，Gemini 会读这段决定调不调",
       parameters={
           "type": "object",
           "properties": {"arg": {"type": "string"}},
           "required": ["arg"],
       },
   )
   ```

2. 加 async handler

   ```python
   async def _handle_my_skill(ctx: SkillCallContext, args: dict) -> dict:
       # ctx.sandbox / ctx.project_manager / ctx.project_name 都已就绪
       ...
       return {"ok": True, ...}
   ```

3. 注册到 `SKILL_DECLARATIONS` 与 `SKILL_HANDLERS` 两张表

4. 写一個测试：参考 `tests/test_skill_function_declarations.py` 的 happy path + 校验失敗 case

5. （可選）让 Gemini 知道这個 skill：description 措辞要明确、要例子。Gemini 偏向直接回答，比 Claude 更需要明确指示「请用 X 工具」

## 如何修改沙盒白名单

`tool_sandbox.py` 顶部：

```python
ALLOWED_SUBDIRS: frozenset[str] = frozenset({"source", "scripts", ...})
ALLOWED_FILES: frozenset[str] = frozenset({"project.json"})
```

**改之前先想清楚**：放宽白名单等于扩大 LLM 写权限。例如允许 `output/` 是 OK 的（成片导出），但不要把 `.agent_data/` 加进来（runtime 内部状态，写坏会导致 session 损坏）。

## 调试 tool call loop

### 看后端实时日志

```bash
docker compose logs arcreel -f --tail 100
```

`gemini-full` 的关键日志：
- `gemini-full: client init failed` — DB 没配 API key
- `gemini-full: generation failed session=...` — generate_content 抛异常（看 traceback）
- `gemini-full: tool X raised` — handler 内部异常

### 跑离线烟雾测试

```bash
docker compose exec arcreel uv run --no-sync python -m scripts.gemini_full_smoketest
```

会建一個 `smoketest-gemini-full` 项目，跑两轮：
1. 让模型调用 `manga_workflow_status` 检查阶段
2. 让模型尝试 `fs_write("/etc/passwd")`，验证沙盒拒绝

### 查 DB transcript

```sql
SELECT seq, substring(payload, 1, 200) FROM agent_messages
WHERE sdk_session_id = 'gemini-full:xxx' ORDER BY seq;
```

`tool_use` / `tool_result` 都会落库。重启后 session 仍可恢复。

## 已知限制

- **subagent 真隔离未实作**：所有 skill dispatch 都跑在主对话同 context；长工作流可能撑大 context。Claude SDK 的「fresh context subagent」未对应实现。
- **permission UI 未接入**：`permission_gate` 默认放行，没有前端 modal 审批。要接入时实作 `PermissionGate.check()` 并 `set_default_gate()`。
- **streaming 仅文本 token**：functionCall / functionResponse 不分块，整体作为一轮事件。
- **parallel tool call 走串行执行**：模型一轮吐多個 functionCall 时按顺序执行；性能差距在 ArcReel 場景里不显著。

## thought_signature 注意事项（Gemini 3 系列）

Gemini 3 系列要求 functionCall 在下一轮回传时携带 `thought_signature`（每個 fc part 的 bytes 字段）。本 provider 已在 `_split_response` 抓取并在拼回 contents 时透传。**自定义 provider 时千万别忘**，否则会得到：

```
400 Bad Request: Function call is missing a thought_signature
```

## 下一步路线图

- [ ] 把占位 skill（generate_storyboard / generate_video / compose_video）接到 generation queue
- [ ] 前端做 banner 切换入口 + Settings 二维 grid 選择器
- [ ] permission_gate 接前端 modal 审批
- [ ] subagent 真隔离（开新 session、回收摘要）
- [ ] OpenAI full-tier provider（同样模式，但用 OpenAI Assistants v2）
