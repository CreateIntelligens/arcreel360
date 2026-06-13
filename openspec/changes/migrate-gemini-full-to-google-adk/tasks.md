## 1. 準備與依賴

- [x] 1.1 在 `pyproject.toml` 新增 `google-adk>=1.32,<1.33` 依賴(鎖 minor)
- [x] 1.2 跑 `uv sync` 驗證 google-adk 與既有 `google-genai` 依賴無衝突
- [x] 1.3 跑 `uv run python -m pytest tests/test_gemini_full_runtime.py -v` 取得遷移前的 baseline,確認 80+ 案例全綠
- [x] 1.4 建立 `docs/adk-upgrade-checklist.md` 範本,列出每次升 google-adk 版本必跑的回歸清單

## 2. AgentMessagesSessionService 實作(Phase 1 spike day 1–4)

> **注意**:任務內容於 design 修訂後重整(原本基於對 `BaseSessionService` API 的不完整理解,參數簽名、抽象方法數量、Event 結構皆有誤)。下方 10 個子任務取代原 7 個;先前若已標 `[x]` 但實際未實作的請重新確認。

- [x] 2.1 新建 `server/agent_runtime/adk_session_service.py`,定義 `AgentMessagesSessionService(BaseSessionService)` 類別骨架,implement 4 個 abstract method 簽名(`create_session` / `get_session` / `list_sessions` / `delete_session` 全部 keyword-only,參數見 design.md Decision 3)
- [x] 2.2 實作 `create_session(*, app_name, user_id, state, session_id)`:`session_id` 為 None 時用 `build_external_session_id("gemini-full", uuid4().hex)` 產生;呼叫既有 `agent_session_repo.create()` 寫入 `agent_sessions`;回傳 pydantic `Session(id, app_name, user_id, state, events=[])`。`app_name="arcreel"`,`user_id` 取對應 project 名
- [x] 2.3 設計 payload wrapper schema:`{"kind": "adk_event", "adk_version": "...", "type": "<推導>", "event": <Event.model_dump_json>}`,實作 `_event_to_payload(event) -> str` 與 `_payload_to_event(payload) -> Event` 兩個 helper(含跨版本降級邏輯)
- [x] 2.4 實作 `append_event(session, event)`(覆寫 base):呼叫 `super().append_event(session, event)` 處理 in-memory state;再呼叫 `_event_to_payload` 序列化後寫入 `agent_messages` 一筆,`seq` 取 max+1
- [x] 2.5 實作 type 推導函式 `_infer_payload_type(event) -> str`:依 design.md 表格(text/tool_use/tool_result/thinking/result/unknown);unknown 在 DEBUG 拋例外、production log warning
- [x] 2.6 實作 `get_session(*, app_name, user_id, session_id, config)`:從 `agent_messages` 讀全部 row(按 `seq` 排序),`_payload_to_event` 反序列化,組成 `Session` 回傳
- [x] 2.7 實作 `list_sessions(*, app_name, user_id)`:從 `agent_sessions` 表查 user 所有 session metadata(不載 events),回傳 `ListSessionsResponse`
- [x] 2.8 實作 `delete_session(*, app_name, user_id, session_id)`:呼叫 `agent_session_repo.delete(session_id)`(FK CASCADE 自動清 `agent_messages`)
- [x] 2.9 新增 `tests/test_adk_session_service.py`,覆蓋:create+get round-trip、append_event 持久化、跨重啟讀回、parallel function call、tool error event、未知 event type DEBUG/production 行為差異、跨 ADK 版本降級讀取(模擬 `adk_version` 不同的 payload)
- [x] 2.10 **Day 4 LOC checkpoint(go/no-go)**:`adk_session_service.py` + `test_adk_session_service.py` 總 LOC 統計;若 > 400 行或實作邊界過多(`list_sessions` 與 `agent_session_repo` 介面不對齊、`Event` 反序列化破口等),走 design.md Decision 3 的「策略 B」fallback:改用 ADK 內建 `InMemorySessionService` + 在 provider 層手動雙寫 events 到 `agent_messages`,並更新 design.md 與 spec 註明採用策略 B

## 3. SkillBaseTool 介面卡(Phase 1 spike day 3–6)

> **注意**:任務內容已對齊 `BaseTool` 真實 API:`__init__(*, name, description, is_long_running, custom_metadata)`、`_get_declaration() -> Optional[FunctionDeclaration]`、`run_async(*, args, tool_context)`(全部 keyword-only)。先前若已標 `[x]` 但實際未實作的請重新確認。

- [x] 3.1 新建 `server/agent_runtime/adk_tool_adapters.py`,定義泛型 `SkillBaseTool(BaseTool)` 類別;`__init__` 接受 `name`、`description`、`declaration: FunctionDeclaration`、`handler: Callable`、`requires_permission: bool`,呼叫 `super().__init__(name=name, description=description)`
- [x] 3.2 覆寫 `_get_declaration() -> Optional[FunctionDeclaration]`:直接回傳建構函式注入的 `FunctionDeclaration`(**禁止**讓 ADK 從 Python signature 自動推導,以保留現有手調 schema)
- [x] 3.3 覆寫 `run_async(*, args: dict, tool_context: ToolContext) -> Any`(注意 keyword-only 簽名):呼叫注入的 handler 並回傳結果(JSON-serializable);任何 exception 包裝成 `{"error": "...", "reason": str(exc)}` 格式以利 ADK Runner 餵回模型
- [x] 3.4 為 7 個 skill 各建立一個 `SkillBaseTool` instance,以 `SKILL_DECLARATIONS` 為輸入資料源(`manga-workflow` / `generate-script` / `generate-storyboard` / `generate-characters` / `generate-clues` / `generate-video` / `compose-video`),`requires_permission=True`
- [x] 3.5 為 `fs_read` / `fs_write` / `fs_list` / `run_subagent` 各建立一個 `SkillBaseTool` instance,內部 handler 呼叫既有 `tool_sandbox` 邏輯;`requires_permission=True`(由 4. permission_gate ADK 介面卡層統一攔截)
- [x] 3.6 **Day 3 LOC checkpoint(go/no-go)**:`SkillBaseTool` 類別 + 11 個 instance 程式碼總計若 > 150 行,go/no-go review
- [x] 3.7 新增 `tests/test_adk_tool_adapters.py`,驗證:每個 instance 的 `_get_declaration()` 回傳與 `SKILL_DECLARATIONS` 中對應條目 `model_dump()` bit-for-bit 一致;`run_async(args=..., tool_context=...)` 正確 dispatch handler;handler 拋例外時回傳 error dict 而非傳播

## 4. permission_gate ADK 介面卡(Phase 1 spike day 5)

> **注意**:`tool` 參數型別為 `BaseTool` instance(透過 `tool.name` 取名);callback 可同步或非同步定義,ADK 會自動 await。先前若已標 `[x]` 但實際未實作的請重新確認。

- [x] 4.1 在 `server/agent_runtime/permission_gate.py` 新增 `as_adk_callback(gate: PermissionGate) -> Callable`,回傳 `(tool: BaseTool, args: dict, tool_context: ToolContext) -> dict | None` 簽名的 callable
- [x] 4.2 callback 內部:`decision = gate.evaluate(tool_name=tool.name, args=args, session_id=tool_context.session_id)`;Allow 時 `return None`(放行);Deny 時 `return {"permission_denied": True, "reason": decision.reason, "tool": tool.name}`(ADK Runner 跳過 tool 執行並把 dict 當 function_response 回模型)
- [x] 4.3 確保 deny dict 經 ADK Runner 包裝為 function_response event 後,被 `AgentMessagesSessionService.append_event` 持久化(payload `type: tool_result`,內含 `permission_denied: true` metadata)
- [x] 4.4 新增 `tests/test_permission_gate_adk.py`:hook 注入後 default policy 全 Allow(callback 回 None)、自訂 deny policy 正確回傳 dict、整合測試確認 ADK Runner 收到 dict 後不執行 tool 而把 dict 當 tool_result 回模型

## 5. AdkGeminiFullRuntimeProvider 主體(Phase 1 spike day 6–10)

> **注意**:`Runner` 真實 API:`Runner(*, agent, app_name, session_service, ...)` + `run_async(*, user_id, session_id, new_message: types.Content, state_delta, run_config) -> AsyncGenerator[Event, None]`。session 必須先透過 `session_service.create_session()` 建好再傳 `session_id` 給 `run_async`。

- [x] 5.1 新建 `server/agent_runtime/adk_gemini_full_runtime_provider.py`,實作 `AssistantRuntimeProvider` 協議
- [x] 5.2 在 provider `__init__` 組裝:`Agent(model=..., tools=[11 個 SkillBaseTool], before_tool_callback=permission_gate.as_adk_callback(gate))`、`AgentMessagesSessionService(...)`、`Runner(agent=agent, app_name="arcreel", session_service=session_service)`
- [x] 5.3 實作 `send_new_session(...)`:呼叫 `session_service.create_session(app_name="arcreel", user_id=<project>)` 建 session;把使用者第一則訊息包成 `types.Content(role="user", parts=[Part(text=...)])`;呼叫 `runner.run_async(user_id=..., session_id=..., new_message=...)` 啟動工具迴圈;最大輪數透過 `RunConfig` 設定(預設 20)
- [x] 5.4 實作 `send_user_message(...)`:同 5.3 但不呼叫 `create_session`(用既有 session_id)
- [x] 5.5 實作 `_project_to_sse(events: AsyncGenerator[Event, None])`:把 ADK Event async iterator 投影到既有 SSE buffer
  - `event.content.parts[*].text`(`partial=True`)→ `stream_event` 增量推送
  - `event.content.parts[*].function_call` → `tool_use` SSE
  - `event.content.parts[*].function_response` → `tool_result` SSE
  - `event.turn_complete` → 終態 SSE
- [x] 5.6 實作 `interrupt_session()`:設一個 cancel flag,讓正在迭代 `run_async()` 產生器的 task 在當前 event 處理完後 break,session 狀態置 `interrupted`
- [x] 5.7 實作心跳超時邏輯:用 `asyncio.wait_for` 包 ADK 事件 iterator 的 `__anext__`,過 `ASSISTANT_STREAM_HEARTBEAT_SECONDS` 無新 event 時取消 stream,session 狀態置 `error`(subtype `timeout`)

## 6. 整合到 service registry(Phase 1 spike day 10–12)

- [x] 6.1 修改 `server/agent_runtime/service.py`:`runtime_provider_registry` 直接註冊 `AdkGeminiFullRuntimeProvider` 取代舊 provider(無 env var、無 if/else 分支;出事透過 git revert 回滾)
- [x] 6.2 (已併入 6.1)
- [x] 6.3 確保 ADK provider 產出的 session_id 前綴仍為 `gemini-full:`,既有 session 仍可讀歷史
- [x] 6.4 新增/驗證 `tests/test_assistant_service_adk_backend.py`,確認 `gemini-full` 路由到 `AdkGeminiFullRuntimeProvider`

## 7. 測試移植與一致性驗證(Phase 1 spike day 11–14)

- [x] 7.1 複製 `tests/test_gemini_full_runtime.py` 為 `tests/test_adk_gemini_full_runtime.py`,把 fixture 改用 ADK provider
- [x] 7.2 跑兩套測試並排,任何 ADK 版本失敗的 case 必須先修(改實作或記錄為 known difference)
- [ ] 7.3 寫一致性測試:同一 prompt 餵兩 provider,比對 SSE 事件序列(允許文字微差,但 tool_use/tool_result 結構必須一致)
- [ ] 7.4 跑 `scripts/gemini_full_smoketest.py` 在 ADK backend 下測試 generate-script 完整工作流,記錄延遲、token 用量
- [ ] 7.5 P50/P95 延遲對比:若 ADK 比 legacy 慢 > 20%,go/no-go review

## 8. Staging 觀察(Phase 2,1 週)

- [ ] 8.1 部署到 staging 環境,監控 SSE 錯誤率、`agent_messages` 寫入異常、`tool_result` payload 結構,連續觀察 7 天
- [ ] 8.2 若有 P1 問題:revert 對應 commit + redeploy,回到 Phase 1 除錯
- [ ] 8.3 7 天無 P1 問題後,進 Phase 3

## 9. 清理 Legacy(Phase 3,1 天)

- [x] 9.1 刪除 `server/agent_runtime/gemini_full_runtime_provider.py`(由本變更直接執行,Phase 3 不需重做)
- [x] 9.2 刪除 `tests/test_gemini_full_runtime.py`(由本變更直接執行;核心 case 已由 `tests/test_adk_gemini_full_runtime.py` 涵蓋)
- [ ] 9.3 把 `tests/test_adk_gemini_full_runtime.py` 改名回 `tests/test_gemini_full_runtime.py`
- [ ] 9.4 更新 `CLAUDE.md` 中 `agent_runtime/` 模組清單:移除 `gemini_full_runtime_provider.py`,新增 `adk_gemini_full_runtime_provider.py` 並註明基於 google-adk
- [ ] 9.5 更新 CHANGELOG.md 記錄遷移完成
- [ ] 9.6 跑全套測試 + smoketest 最後驗證 + 走 archive 流程(`/opsx:archive migrate-gemini-full-to-google-adk`)
