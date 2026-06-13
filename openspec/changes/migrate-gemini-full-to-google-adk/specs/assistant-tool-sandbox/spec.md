## MODIFIED Requirements

### Requirement: fs_read 工具契約

`fs_read(path: str, max_bytes: int = 1048576) -> {"content": str, "bytes_read": int, "truncated": bool}`:從沙盒中讀取文字檔案,超過 `max_bytes`(預設 1 MiB)時 MUST 截斷並標記 `truncated=true`。MUST 僅支援 UTF-8 文字;二進位檔案 MUST 回傳 `{"error": "binary_file"}`。

**新增實作約束**:此工具 MUST 實作為 ADK `BaseTool` 子類,**不**使用 `FunctionTool` 的自動 signature 推導;`_get_declaration()` MUST 直接回傳手調的 `FunctionDeclaration`,保留現有 schema 描述措辭與 parameter 命名。

#### Scenario: 正常讀取
- **WHEN** 工具呼叫 `fs_read("scripts/episode_1.json")`,檔案 50 KB
- **THEN** 回傳 `{"content": "...", "bytes_read": 50000, "truncated": false}`

#### Scenario: 超大檔案截斷
- **WHEN** 檔案 5 MB
- **THEN** 回傳 `{"content": "<前 1 MB>", "bytes_read": 1048576, "truncated": true}`

#### Scenario: ADK BaseTool 子類正確注入
- **WHEN** ADK `Agent(tools=[fs_read_tool, ...])` 啟動
- **THEN** `Agent.list_tools()` MUST 含 `fs_read`,且其 `_get_declaration()` 回傳的 `FunctionDeclaration.parameters` 與 `SKILL_DECLARATIONS` 中的對應條目 bit-for-bit 一致

### Requirement: fs_write 工具契約

`fs_write(path: str, content: str, mode: "create" | "overwrite" = "overwrite") -> {"bytes_written": int, "created": bool}`:寫入文字檔案,單檔案 MUST 限制在 10 MiB 以內。`mode="create"` 時若檔案已存在 MUST 拒絕。父目錄不存在 MUST 自動建立(僅在白名單內)。

**新增實作約束**:此工具 MUST 實作為 ADK `BaseTool` 子類,內部呼叫既有 `tool_sandbox` 模組的核心邏輯。

#### Scenario: 建立新檔案
- **WHEN** 工具呼叫 `fs_write("scripts/episode_2.json", "{...}")`,檔案不存在
- **THEN** 建立檔案,回傳 `{"bytes_written": <n>, "created": true}`

#### Scenario: create 模式下檔案已存在
- **WHEN** 工具呼叫 `fs_write("scripts/episode_1.json", "...", mode="create")`,檔案已存在
- **THEN** 拒絕並回傳 `{"error": "already_exists"}`

#### Scenario: 內容超限
- **WHEN** content 長度超過 10 MiB
- **THEN** 拒絕 `{"error": "content_too_large", "limit": 10485760}`

### Requirement: fs_list 工具契約

`fs_list(path: str) -> {"entries": [{"name": str, "is_dir": bool, "size": int}]}`:列出目錄下條目,僅顯示直接子項,不遞迴。`path` MUST 是白名單子目錄之一。條目按名字升序排列。隱藏檔案(以 `.` 開頭)MUST 過濾掉。

**新增實作約束**:此工具 MUST 實作為 ADK `BaseTool` 子類。

#### Scenario: 列出 source 目錄
- **WHEN** 工具呼叫 `fs_list("source")`
- **THEN** 回傳 `{"entries": [{"name": "chapter1.txt", "is_dir": false, "size": 12345}, ...]}`,不含 `.git` `.DS_Store` 等隱藏項

#### Scenario: 列出非白名單目錄
- **WHEN** 工具呼叫 `fs_list(".agent_data")`
- **THEN** 拒絕

### Requirement: run_subagent 工具契約

`run_subagent(skill: str, args: dict) -> {"result": <serializable>, "error": str | null}`:dispatch 一個 skill subagent 並同步等待回傳。`skill` MUST 是 `manga-workflow` / `generate-script` / `generate-storyboard` / `generate-characters` / `generate-clues` / `generate-video` / `compose-video` 之一。skill 實際行為由 `skill_function_declarations.py` 註冊的 handler 決定。

**新增實作約束**:7 個 skill MUST 各自實作為 ADK `BaseTool` 子類(或共用一個泛型 `SkillBaseTool` 類的 7 個 instance),覆寫 `_get_declaration()` 回傳對應 `SKILL_DECLARATIONS` 中的手調 schema。`run_subagent` 概念上等同於 ADK Runner 自動執行對應 `BaseTool`,但對 LLM 暴露的 function name 仍為各 skill 名稱(非 `run_subagent` 包裝層)。

#### Scenario: 合法 skill 呼叫
- **WHEN** 模型回傳 `functionCall(name="generate_script", args={"episode": 1, "source_files": ["chapter1.txt"]})`
- **THEN** ADK Runner dispatch 對應 `SkillBaseTool` instance,內部呼叫既有 handler,結果序列化後以 `function_response` event 回模型

#### Scenario: 未註冊 skill
- **WHEN** 模型回傳 `functionCall` name 不在 7 個 skill 註冊清單中
- **THEN** ADK 在 declaration 階段就會拒絕該 functionCall(因 `Agent.tools` 列表不含此名稱),不會走到 `run_subagent` 邏輯

### Requirement: PreToolUse 權限閘門必須支援掛載與預設放行

系統 SHALL 在每次工具執行前透過 ADK `before_tool_callback(tool, args, tool_context)` hook 呼叫 `permission_gate.evaluate(tool_name, args, session_id)`,閘門回傳 `Allow` / `Deny(reason)` / `AskUser(question)`。預設實作 MUST 全部回傳 `Allow`,但介面 MUST 支援執行階段掛載自訂實作以便未來加入 UI 審批。

**新增實作約束**:整合路徑 MUST 由 ADK `before_tool_callback` 注入,不再在 provider 主迴圈中手動呼叫;`permission_gate.py` MUST 新增 `as_adk_callback(gate: PermissionGate) -> Callable` 介面卡函式回傳 ADK 相容簽名。

#### Scenario: 預設放行
- **GIVEN** 未掛載自訂 gate
- **WHEN** 任意工具呼叫前
- **THEN** `before_tool_callback` 回傳 `None`,ADK Runner 繼續執行 tool

#### Scenario: Deny 時 functionResponse 攜帶原因
- **GIVEN** 自訂 gate 對 `fs_write` 回傳 `Deny("user rejected")`
- **WHEN** 模型呼叫 `fs_write`
- **THEN** `before_tool_callback` 回傳 `{"permission_denied": true, "reason": "user rejected", "tool": "fs_write"}` dict;ADK Runner MUST 跳過該 tool 執行,把 dict 當 function_response 餵回模型;模型 MAY 選擇換路或終止

#### Scenario: Deny 不拋例外
- **WHEN** gate 拒絕
- **THEN** session 狀態保持 `running`,不進入 `error`,對話流不中斷;deny 事件 MUST 持久化為 `tool_result` 類型訊息(payload 含 `permission_denied: true` metadata)
