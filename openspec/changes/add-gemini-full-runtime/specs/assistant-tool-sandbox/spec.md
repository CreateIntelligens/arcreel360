## ADDED Requirements

### Requirement: 沙盒必须把可访问根目录限定为 projects/{project_name}/

系统 SHALL 提供 `ToolSandbox` 模块，所有助手工具的文件 IO MUST 经其校验。沙盒根 MUST 是当前 session 所属 project 的 `projects/{project_name}/` 绝对路径。任何超出该根目录的访问 MUST 在工具执行前被拒绝。

#### Scenario: 越界写入被拒
- **WHEN** 工具试图 `fs_write("/etc/passwd", ...)` 或 `fs_write("../../foo", ...)`
- **THEN** 沙盒 MUST 抛出 `SandboxViolationError` 或返回结构化错误 `{"error": "sandbox_violation", "reason": "path outside project root"}`，不执行任何写入

#### Scenario: 越界读取被拒
- **WHEN** 工具试图 `fs_read("/app/.venv/...")` 或 `fs_read("../other-project/project.json")`
- **THEN** 同上拒绝

### Requirement: 沙盒必须用白名单控制项目内可访问的子目录

在项目根目录内，访问 MUST 进一步限定到下列白名单子目录或文件之一：`source/`、`scripts/`、`characters/`、`clues/`、`storyboards/`、`videos/`、`drafts/`、`output/`、`project.json`。其它路径（如 `.arcreel.db`、`.agent_data/`、`.git/` 等）MUST 拒绝。

#### Scenario: 白名单内合法访问
- **WHEN** 工具调用 `fs_write("scripts/episode_1.json", "...")`，project_name 已知为 `demo`
- **THEN** 沙盒 MUST 把请求重写为 `projects/demo/scripts/episode_1.json` 并允许执行

#### Scenario: 白名单外路径拒绝
- **WHEN** 工具调用 `fs_read(".arcreel.db")` 或 `fs_list(".agent_data/")`
- **THEN** 拒绝并返回 `{"error": "not_in_whitelist", "reason": "..."}`，不暴露底层路径

#### Scenario: project.json 是单文件白名单
- **WHEN** 工具调用 `fs_read("project.json")` 或 `fs_write("project.json", ...)`
- **THEN** 允许，但 `fs_list("project.json")` MUST 拒绝（不是目录）

### Requirement: 路径校验必须用绝对路径解析后再判断

沙盒 MUST 对每次请求执行 `Path(project_root) / project_name / req_path`，再调用 `.resolve(strict=False)` 拿到绝对路径，最后用 `is_relative_to(allowed_root)` 校验。校验 MUST 在符号链接解析后执行，确保链接指向白名单外时仍被拒绝。

#### Scenario: 符号链接不能绕过沙盒
- **GIVEN** `projects/demo/source/link-to-secrets` 是指向 `/etc/secrets` 的符号链接
- **WHEN** 工具调用 `fs_read("source/link-to-secrets")`
- **THEN** 沙盒 MUST resolve 后发现真实目标在白名单外，拒绝访问

#### Scenario: 不存在路径的查询不泄露路径结构
- **WHEN** 工具调用 `fs_read("source/nonexistent.txt")`
- **THEN** 返回 `{"error": "not_found"}`，不携带绝对路径或目录结构信息

### Requirement: fs_read 工具契约

`fs_read(path: str, max_bytes: int = 1048576) -> {"content": str, "bytes_read": int, "truncated": bool}`：从沙盒中读取文本文件，超过 `max_bytes`（默认 1 MiB）时 MUST 截断并标记 `truncated=true`。MUST 仅支持 UTF-8 文本；二进制文件 MUST 返回 `{"error": "binary_file"}`。

#### Scenario: 正常读取
- **WHEN** 工具调用 `fs_read("scripts/episode_1.json")`，文件 50 KB
- **THEN** 返回 `{"content": "...", "bytes_read": 50000, "truncated": false}`

#### Scenario: 超大文件截断
- **WHEN** 文件 5 MB
- **THEN** 返回 `{"content": "<前 1 MB>", "bytes_read": 1048576, "truncated": true}`

### Requirement: fs_write 工具契约

`fs_write(path: str, content: str, mode: "create" | "overwrite" = "overwrite") -> {"bytes_written": int, "created": bool}`：写入文本文件，单文件 MUST 限制在 10 MiB 以内。`mode="create"` 时若文件已存在 MUST 拒绝。父目录不存在 MUST 自动创建（仅在白名单内）。

#### Scenario: 创建新文件
- **WHEN** 工具调用 `fs_write("scripts/episode_2.json", "{...}")`，文件不存在
- **THEN** 创建文件，返回 `{"bytes_written": <n>, "created": true}`

#### Scenario: create 模式下文件已存在
- **WHEN** 工具调用 `fs_write("scripts/episode_1.json", "...", mode="create")`，文件已存在
- **THEN** 拒绝并返回 `{"error": "already_exists"}`

#### Scenario: 内容超限
- **WHEN** content 长度超过 10 MiB
- **THEN** 拒绝 `{"error": "content_too_large", "limit": 10485760}`

### Requirement: fs_list 工具契约

`fs_list(path: str) -> {"entries": [{"name": str, "is_dir": bool, "size": int}]}`：列出目录下条目，仅显示直接子项，不递归。`path` MUST 是白名单子目录之一。条目按名字升序排列。隐藏文件（以 `.` 开头）MUST 过滤掉。

#### Scenario: 列出 source 目录
- **WHEN** 工具调用 `fs_list("source")`
- **THEN** 返回 `{"entries": [{"name": "chapter1.txt", "is_dir": false, "size": 12345}, ...]}`，不含 `.git` `.DS_Store` 等隐藏项

#### Scenario: 列出非白名单目录
- **WHEN** 工具调用 `fs_list(".agent_data")`
- **THEN** 拒绝

### Requirement: run_subagent 工具契约

`run_subagent(skill: str, args: dict) -> {"result": <serializable>, "error": str | null}`：dispatch 一個 skill subagent 并同步等待返回。`skill` MUST 是 `manga-workflow` / `generate-script` / `generate-storyboard` / `generate-characters` / `generate-clues` / `generate-video` / `compose-video` 之一。skill 实际行为由 `skill_function_declarations.py` 注册的 handler 决定。

#### Scenario: 合法 skill 调用
- **WHEN** 工具调用 `run_subagent("generate_script", {"episode": 1, "source_files": ["chapter1.txt"]})`
- **THEN** 系统 dispatch 对应 handler，同步阻塞直到返回，结果序列化后返回模型

#### Scenario: 未注册 skill
- **WHEN** 工具调用 `run_subagent("unknown_skill", {})`
- **THEN** 拒绝 `{"error": "unknown_skill", "available": [...]}`

### Requirement: PreToolUse 权限闸门必须支持挂载与默认放行

系统 SHALL 在每次工具执行前调用 `permission_gate.check(tool_name, args, session_id)`，闸门返回 `Allow` / `Deny(reason)` / `AskUser(question)`。默认实现 MUST 全部返回 `Allow`，但接口 MUST 支持运行时挂载自定义实现以便未来加入 UI 审批。

#### Scenario: 默认放行
- **GIVEN** 未挂载自定义 gate
- **WHEN** 任意工具调用前
- **THEN** gate 返回 `Allow`，工具继续执行

#### Scenario: Deny 时 functionResponse 携带原因
- **GIVEN** 自定义 gate 对 `fs_write` 返回 `Deny("user rejected")`
- **WHEN** 模型调用 `fs_write`
- **THEN** 系统 NOT 执行写入，构造 `functionResponse(name="fs_write", response={"error": "permission_denied", "reason": "user rejected"})` 喂回模型；模型 MAY 選择换路或终止

#### Scenario: Deny 不抛异常
- **WHEN** gate 拒绝
- **THEN** session 状态保持 `running`，不进入 `error`，对话流不中断
