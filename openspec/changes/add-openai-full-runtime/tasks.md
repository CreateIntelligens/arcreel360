## 1. 準備與依賴

- [x] 1.1 在 `pyproject.toml` 新增 `openai-agents>=0.1,<0.2` 依賴(版本依 spike 確認結果調整)
- [x] 1.2 跑 `uv sync` 驗證 `openai-agents` 與既有 `openai` SDK 無衝突
- [x] 1.3 跑 `uv run python -m pytest tests/test_assistant_*.py -v` 取得 baseline,確認所有既有 assistant 相關測試全綠
- [x] 1.4 建立 `docs/openai-agents-upgrade-checklist.md` 範本,列出每次升 `openai-agents` 版本必跑的回歸清單

## 2. Schema 轉換器與 Tool Adapter(Phase 1 spike day 1–4)

- [x] 2.1 新建 `server/agent_runtime/openai_tool_adapters.py`,實作 `_gemini_to_openai_schema(parameters: dict) -> dict`:把 Google `FunctionDeclaration.parameters`(`Type` enum、巢狀)轉成 OpenAI JSON Schema dialect(字串 type、`additionalProperties: false`)
- [x] 2.2 寫 `tests/test_openai_tool_adapters.py`,對 11 個工具(7 skill + 4 fs)各做 round-trip schema 轉換測試;驗證輸出符合 OpenAI Agents SDK strict mode 要求
- [x] 2.3 實作 `build_skill_tools(declarations: list[FunctionDeclaration], handlers: dict, gate: PermissionGate) -> list[FunctionTool]` 工廠函式,把每個 declaration 包成 `FunctionTool(name, description, params_json_schema, on_invoke_tool)`
- [x] 2.4 `on_invoke_tool` callback MUST 透過 `permission_gate.as_openai_wrapper(gate, tool_name)` 包裝,deny 時回傳 dict
- [x] 2.5 用真實 OpenAI API key 跑 spike:組裝 `Agent` + 11 個 FunctionTool,用 GPT-4o 觸發單一 `generate_script` tool call,驗證 args 結構與既有 Gemini 測試一致

## 3. Permission Gate 介面卡(Phase 1 spike day 4)

- [x] 3.1 在 `server/agent_runtime/permission_gate.py` 新增 `as_openai_wrapper(gate: PermissionGate, tool_name: str) -> Callable`
- [x] 3.2 wrapper 簽名:`async def wrapped(ctx, args) -> dict`;Allow 時透傳給原 handler、Deny 時回傳 `{"permission_denied": True, "reason": ..., "tool": tool_name}`
- [x] 3.3 寫測試:default policy 全 Allow、自訂 deny policy 正確包裝、deny 後 SDK Runner 把 dict 當 tool_result 回模型(不執行 handler)
- [x] 3.4 驗證 deny 後寫入的 `tool_result` payload 與 `gemini-full`(ADK) provider 的 canonical deny dict 形狀一致

## 4. OpenAIFullRuntimeProvider 主體(Phase 1 spike day 5–9)

- [x] 4.1 新建 `server/agent_runtime/openai_full_runtime_provider.py`,實作 `AssistantRuntimeProvider` 協議
- [x] 4.2 在 provider `__init__` 組裝 `Agent`:tools=`build_skill_tools(SKILL_DECLARATIONS, SKILL_HANDLERS, gate)`,model=從 config 讀取(預設 `gpt-4o`),instructions=skill system prompt
- [x] 4.3 實作 `send_new_session(...)`:用 `build_external_session_id("openai-full", uuid_hex)` 生成 session id,寫入 `agent_messages` 起始記錄
- [x] 4.4 實作 `send_user_message(...)`:從 `agent_messages` 讀完整歷史,轉成 OpenAI Agents SDK input list 格式(role + content),呼叫 `Runner.run_streamed(agent, input=history, session=None, max_turns=20)`
- [x] 4.5 確保 `session=None`:寫 unit test 守住此不變式(誤傳非 None 值會被攔截)
- [x] 4.6 實作 `_project_to_sse(events)`:把 SDK 的 `RunItem` / `RawResponseStreamEvent` async iterator 投影到既有 SSE buffer
  - `MessageOutputItem`(text delta)→ `stream_event` 增量推送
  - `ToolCallItem` → `tool_use` SSE + `agent_messages` 寫入
  - `ToolCallOutputItem` → `tool_result` SSE + `agent_messages` 寫入
  - `RunCompleteEvent` → 終態 SSE + `agent_messages` 寫入彙總 `assistant` 訊息
- [x] 4.7 實作 `interrupt_session()`:在當前 tool 執行完後停止 Runner 啟動下一輪
- [x] 4.8 實作心跳超時邏輯:SDK Runner 過 `ASSISTANT_STREAM_HEARTBEAT_SECONDS` 無新 event 時取消 stream

## 5. Session Identity 與 Service Registry 整合

- [x] 5.1 修改 `server/agent_runtime/session_identity.py`:新增 `OPENAI_FULL_PROVIDER_ID = "openai-full"` 常數;`infer_provider_id` 支援 `openai-full:` 前綴;確認 `openai:` 前綴仍對應 `openai-lite`
- [x] 5.2 修改 `server/agent_runtime/service.py`:`runtime_provider_registry["openai-full"] = OpenAIFullRuntimeProvider(...)`;`_resolve_active_provider_id` 接受新值
- [x] 5.3 寫 `tests/test_session_identity_openai_full.py`:覆蓋新前綴 routing 與舊 lite session 不被誤路由

## 6. 前端 UI 整合

- [x] 6.1 修改 `frontend/src/components/pages/AgentConfigTab.tsx`:`RUNTIME_MATRIX["openai"]["full"]` 從 `null` 改為 `"openai-full"`
- [x] 6.2 在 `ASSISTANT_PROVIDER_META` 新增 `"openai-full"` 條目:label `OpenAI · 工作流模式`、tier `full`、description 描述能呼叫 7 個 skill、requirement 描述需設定 OpenAI API key
- [x] 6.3 修改 `frontend/src/types/assistant.ts`:`ASSISTANT_PROVIDER_LABELS` 新增 `openai-full`;`inferAssistantProvider` 支援 `openai-full:` 前綴
- [x] 6.4 跑前端 typecheck `node_modules/.bin/tsc --noEmit -p .` 確認零錯誤
- [x] 6.5 跑 `frontend/src/components/pages/AgentConfigTab.test.tsx`(若存在)確認 UI 整合測試通過

## 7. 整合測試與一致性驗證(Phase 1 spike day 10–11)

- [x] 7.1 寫 `tests/test_openai_full_runtime.py`,類比 `test_gemini_full_runtime.py` 的測試結構,覆蓋:capabilities tier=full、session id 前綴、單輪/多輪 tool call、permission deny、interrupt、心跳超時、歷史重放
- [ ] 7.2 端到端測試:用 OpenAI provider 跑完整 manga 工作流(generate-script + generate-storyboard),記錄延遲、token 用量
- [x] 7.3 一致性測試:相同 prompt 與 deny policy 餵 `gemini-full` 與 `openai-full`,比對 SSE 事件序列(允許文字微差,但 tool_use/tool_result/permission_denied 結構必須一致)
- [x] 7.4 確認所有 `tests/test_session_identity_*.py` 與 `tests/test_assistant_service_*.py` 跑全套通過

## 8. 文件與上線(Phase 2 + 3,~3 天)

- [x] 8.1 更新 `CLAUDE.md` 中 `agent_runtime/` 模組清單:新增 `openai_full_runtime_provider.py` 與 `openai_tool_adapters.py`;在「核心模組」段補上 `openai-full` 行(tier=full,基於 openai-agents)
- [x] 8.2 更新 `CLAUDE.md` 中 Agent Runtime 表格,把 `openai-full` 加入(tier=full、模式=工作流、說明=OpenAI Agents SDK 工具循環)
- [x] 8.3 更新 `.env.example`:`ASSISTANT_PROVIDER` 註解列出 `openai-full` 為新合法值
- [x] 8.4 更新 `CHANGELOG.md`:記錄 OpenAI 升級到 full tier
- [ ] 8.5 部署到 staging 環境,使用者主動切換到 `openai-full` 後 smoke test
- [ ] 8.6 監控 SSE 錯誤率、`agent_messages` 寫入異常 7 天
- [ ] 8.7 7 天無 P1 問題後:走 archive 流程(`/opsx:archive add-openai-full-runtime`)
