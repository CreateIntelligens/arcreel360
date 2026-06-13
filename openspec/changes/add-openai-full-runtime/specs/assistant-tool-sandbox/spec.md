## MODIFIED Requirements

### Requirement: fs_read 工具契約

`fs_read(path: str, max_bytes: int = 1048576) -> {"content": str, "bytes_read": int, "truncated": bool}`:從沙盒中讀取文字檔案,超過 `max_bytes`(預設 1 MiB)時 MUST 截斷並標記 `truncated=true`。MUST 僅支援 UTF-8 文字;二進位檔案 MUST 回傳 `{"error": "binary_file"}`。

**新增實作約束**:在 `openai-full` provider 中,此工具 MUST 包裝為 `openai_agents.FunctionTool`,`params_json_schema` 直接複用 `SKILL_DECLARATIONS["fs_read"]` 中的手調 schema(經 `_gemini_to_openai_schema()` 轉換成 OpenAI JSON Schema dialect)。`on_invoke_tool` callback MUST 呼叫既有 `tool_sandbox` 模組的核心邏輯,維持與其他 provider 的行為一致。

#### Scenario: 正常讀取
- **WHEN** 工具呼叫 `fs_read("scripts/episode_1.json")`,檔案 50 KB
- **THEN** 回傳 `{"content": "...", "bytes_read": 50000, "truncated": false}`

#### Scenario: 超大檔案截斷
- **WHEN** 檔案 5 MB
- **THEN** 回傳 `{"content": "<前 1 MB>", "bytes_read": 1048576, "truncated": true}`

#### Scenario: schema 轉換正確性
- **WHEN** `_gemini_to_openai_schema(SKILL_DECLARATIONS["fs_read"].parameters)` 執行
- **THEN** 結果 MUST 是合法的 OpenAI JSON Schema(`type` 為字串而非 enum、`additionalProperties` 預設為 `false`、巢狀正確);GPT 模型測試呼叫 MUST 產生與既有 Gemini 測試相同形狀的 args

### Requirement: fs_write 工具契約

`fs_write(path: str, content: str, mode: "create" | "overwrite" = "overwrite") -> {"bytes_written": int, "created": bool}`:寫入文字檔案,單檔案 MUST 限制在 10 MiB 以內。`mode="create"` 時若檔案已存在 MUST 拒絕。父目錄不存在 MUST 自動建立(僅在白名單內)。

**新增實作約束**:在 `openai-full` provider 中,此工具 MUST 包裝為 `openai_agents.FunctionTool`,內部呼叫既有 `tool_sandbox` 模組。

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

**新增實作約束**:在 `openai-full` provider 中,此工具 MUST 包裝為 `openai_agents.FunctionTool`。

#### Scenario: 列出 source 目錄
- **WHEN** 工具呼叫 `fs_list("source")`
- **THEN** 回傳 `{"entries": [{"name": "chapter1.txt", "is_dir": false, "size": 12345}, ...]}`,不含 `.git` `.DS_Store` 等隱藏項

#### Scenario: 列出非白名單目錄
- **WHEN** 工具呼叫 `fs_list(".agent_data")`
- **THEN** 拒絕

### Requirement: run_subagent 工具契約

`run_subagent(skill: str, args: dict) -> {"result": <serializable>, "error": str | null}`:dispatch 一個 skill subagent 並同步等待回傳。`skill` MUST 是 `manga-workflow` / `generate-script` / `generate-storyboard` / `generate-characters` / `generate-clues` / `generate-video` / `compose-video` 之一。skill 實際行為由 `skill_function_declarations.py` 註冊的 handler 決定。

**新增實作約束**:在 `openai-full` provider 中,7 個 skill MUST 各自包裝為 `openai_agents.FunctionTool` instance,直接以 skill 名稱對外曝露(不透過 `run_subagent` 包裝)。`params_json_schema` 來源為 `SKILL_DECLARATIONS` 對應條目經 `_gemini_to_openai_schema()` 轉換。`on_invoke_tool` callback MUST 透過 `permission_gate.as_openai_wrapper()` 包裝,deny 時回傳 `{"permission_denied": True, ...}` dict,不執行 handler。

#### Scenario: 合法 skill 呼叫
- **WHEN** 模型回傳 tool call(name=generate_script, args={"episode": 1, "source_files": ["chapter1.txt"]})
- **THEN** SDK Runner dispatch 對應 FunctionTool,`on_invoke_tool` 內部呼叫既有 handler,結果序列化後以 `ToolCallOutputItem` 回模型

#### Scenario: 未註冊 skill
- **WHEN** 模型回傳 tool call name 不在 7 個 skill 註冊清單中
- **THEN** SDK 在 declaration 階段拒絕該 tool call(`Agent.tools` 列表不含此名稱)

### Requirement: PreToolUse 權限閘門必須支援掛載與預設放行

系統 SHALL 在每次工具執行前透過 OpenAI Agents SDK 的 `on_invoke_tool` 包裝層呼叫 `permission_gate.evaluate(tool_name, args, session_id)`,閘門回傳 `Allow` / `Deny(reason)` / `AskUser(question)`。預設實作 MUST 全部回傳 `Allow`,但介面 MUST 支援執行階段掛載自訂實作以便未來加入 UI 審批。

**新增實作約束**:由於 OpenAI Agents SDK 沒有等價於 ADK `before_tool_callback` 的中心化 hook,整合路徑改為 `on_invoke_tool` 包裝層。`permission_gate.py` MUST 新增 `as_openai_wrapper(gate: PermissionGate, tool_name: str) -> Callable` 介面卡函式,回傳一個包裝既有 handler 的 callable;deny 時跳過 handler 直接回傳 dict,Allow 時透傳給原 handler。

#### Scenario: 預設放行
- **GIVEN** 未掛載自訂 gate
- **WHEN** 任意工具呼叫前
- **THEN** 包裝層判定 Allow,透傳給原 handler 執行

#### Scenario: Deny 時 tool_result 攜帶原因
- **GIVEN** 自訂 gate 對 `fs_write` 回傳 `Deny("user rejected")`
- **WHEN** 模型呼叫 `fs_write`
- **THEN** 包裝層 NOT 執行寫入,回傳 `{"permission_denied": True, "reason": "user rejected", "tool": "fs_write"}` dict;SDK Runner 把 dict 當 tool output 餵回模型;模型 MAY 選擇換路或終止

#### Scenario: Deny 不拋例外
- **WHEN** gate 拒絕
- **THEN** session 狀態保持 `running`,不進入 `error`,對話流不中斷;deny 事件 MUST 持久化為 `tool_result` 類型訊息(payload 含 `permission_denied: true` metadata)

#### Scenario: Deny 行為與其他 provider 1:1 對齊
- **GIVEN** 同一 deny scenario 在 `gemini-full`(ADK)與 `openai-full` 上各跑一次
- **THEN** 兩 provider 寫入 `agent_messages` 的 `tool_result` payload 中，permission deny 部分(`permission_denied: true`、`reason`、`tool` 三個欄位)MUST bit-for-bit 一致；不要求與 pre-ADK legacy 形狀對齊
