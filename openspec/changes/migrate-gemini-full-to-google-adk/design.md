## Context

`gemini-full` 目前實作(commit `59d78eb` 引入)由四個模組構成,共 ~1770 LOC,全部位於 `server/agent_runtime/`:

| 模組 | LOC | 目前職責 |
|---|---|---|
| `gemini_full_runtime_provider.py` | 659 | `Runner` 等價物:自維護工具循環、`generate_content_stream` chunk 解析、`functionCall` / `functionResponse` 配對、`thought_signature` 透傳、流式事件投影到 SSE |
| `tool_sandbox.py` | 245 | 白名單沙盒(fs_read / fs_write / fs_list),路徑正規化、越界檢查 |
| `permission_gate.py` | 105 | PreToolUse 風格閘門:deny 時把原因塞回 `functionResponse`,不中斷對話 |
| `skill_function_declarations.py` | 762 | 7 個 skill 的 `FunctionDeclaration` 手調 schema + handler dispatch |

Anthropic Claude provider 使用官方 `claude_agent_sdk`,享有 SDK 維護紅利;Gemini 這邊長期承擔「等價 Claude SDK 內部行為」的自研負擔。Google 在 2025 年發布 `google-adk`(Gen AI Agent Development Kit)作為 Gemini 官方 agent 框架,核心抽象 `Agent` / `Runner` / `BaseTool` / `BaseSessionService` / `before_tool_callback` 與本專案自刻概念幾乎一一對應。

約束:
- 既有 7 個 skill 的 `FunctionDeclaration.parameters` 是經過反覆 prompt-tuning 的,schema 描述措辭、parameter 命名都直接影響模型行為;不可被 ADK 的 `FunctionTool` 自動 signature 推導覆蓋。
- session 持久化已用 `agent_messages` 表(跨 provider 共用),不能切換到 ADK 內建 `InMemorySessionService` / `DatabaseSessionService` —— 否則舊 session 讀不出來,且製造雙 source-of-truth。
- 對外契約(HTTP API、SSE 事件、capability matrix、session_id 前綴)必須零破壞。
- `google-adk` 仍在快速迭代(雙週發版,1.32.0),breaking change 風險顯著。

利益相關方:後端工程師(實作遷移)、前端(零改動驗證)、運維(feature flag 切換 + 回滾)、最終使用者(`gemini-full` 行為應與遷移前一致)。

## Goals / Non-Goals

**Goals:**

- 把 `gemini-full` 的工具循環底座從自刻替換為 `google-adk`,回收 ~250–350 行自維護程式碼(工具循環 + chunk parsing + functionCall 配對)。
- 與 `claude` provider 在策略層對齊:「各家 full-tier provider 使用各家官方 agent SDK」。
- 保留所有現有 prompt-tuning 投資:7 個 skill 的手調 schema 一字不動。
- 保留 `agent_messages` 表作為 session 唯一真相源;ADK session 透過 custom `BaseSessionService` 橋接。
- 直接切換,不引入 feature flag(避免把實作細節洩漏成使用者設定);出事透過 git revert + redeploy 回滾。
- 現有 80+ 個 `tests/test_gemini_full_runtime.py` 測試核心 case 由 `tests/test_adk_gemini_full_runtime.py` 移植涵蓋。

**Non-Goals:**

- **不**統一所有 provider 到單一框架。design 沿用 `add-gemini-full-runtime` 時的判斷(design.md line 65 警告「框架反而會變成只服務 Gemini 的偽抽象」):claude 仍走 Anthropic SDK,openai 在另一變更(`add-openai-full-runtime`)走 OpenAI Agents SDK。
- **不**引入 ADK live streaming(`Runner.run_live()` 標記 experimental),本次僅用 `Runner.run_async()` 事件流。
- **不**藉機重構 `tool_sandbox` 業務邏輯:白名單規則、路徑解析行為保持現狀,只是從「主迴圈直接呼叫」變成「ADK BaseTool 內部呼叫」。
- **不**改前端:`AgentCopilot` / `AgentConfigTab` / `useAssistantSession` 零改動;capability matrix 資料流不變。
- **不**觸碰其他 capability spec:`workflow-orchestration` / `assistant-runtime-selection` 不需要修改。

## Decisions

### 1. 沿用 `provider_id="gemini-full"`,新建 `adk_gemini_full_runtime_provider.py` 直接取代舊實作

**選擇**:新檔案 `adk_gemini_full_runtime_provider.py` 實作新版;Phase 1 spike 期間兩檔並存供 LOC checkpoint 與測試對比,Phase 3 直接刪除 `gemini_full_runtime_provider.py`,registry 直接指向 ADK provider。**不引入** `ASSISTANT_GEMINI_FULL_BACKEND` 之類的 env var,避免把實作細節洩漏成使用者設定。

**替代方案**:

- 直接在原檔 in-place 重寫。**否決**:單 PR 改動 1500+ 行難以 review。
- 用 feature flag(`ASSISTANT_GEMINI_FULL_BACKEND=legacy|adk`)兩週並存。**否決**:env var 把實作切換暴露給運維/使用者,長期維護雙實作成本高;直接切換出事 git revert 一樣快。

**理由**:spike 階段 spike provider 與 legacy 並排可在 commit 歷史內驗證一致性;Phase 3 直接刪除 legacy,registry 直接指向 ADK,避免技術債與使用者層級的實作開關。

### 2. 7 個 skill 用 `BaseTool` 子類(覆寫 `_get_declaration`),不用 `FunctionTool`

**選擇**:實作一個泛型 `SkillBaseTool(BaseTool)` 類,建構函式參數化(`name` / `declaration` / `handler` / `requires_permission`),覆寫:

```python
def _get_declaration(self) -> FunctionDeclaration:
    return self._declaration  # 直接回傳 SKILL_DECLARATIONS 中的手調 schema

async def run_async(self, args, tool_context):
    return await self._handler(ctx=..., args=args)  # 複用既有 handler
```

然後在 `adk_tool_adapters.py` 用 `SKILL_DECLARATIONS` 作為輸入資料源建立 7 個 instance。

**替代方案**:

- 用 `FunctionTool(func)`。**否決**:ADK 強制從 Python signature 自動推導 schema(`FunctionTool._get_declaration()` 內部行為),會丟失現有 schema 描述措辭、parameter 命名細節,prompt-tuning 投資歸零。
- 為每個 skill 各寫一個 class。**否決**:7 個 class 樣板程式碼太多,違反 DRY。

**理由**:用一個泛型類減少樣板程式碼,預估 7 個 adapter 總計 ~50–80 LOC(vs 現有 `_dispatch_function_call` 的 ~80 LOC,持平或略省)。**Phase 1 spike 必須實測此預估**:若總計 > 現有 `FunctionDeclaration` 轉換 + dispatch(~150 LOC),整個遷移取消。

### 3. Custom `BaseSessionService` 橋接 ADK session events ↔ `agent_messages` 表

**ADK 真實 API 簽名**(`google.adk.sessions.BaseSessionService`,verified against 1.32.0):

```python
class BaseSessionService(abc.ABC):
    async def create_session(self, *, app_name: str, user_id: str,
                             state: Optional[dict] = None,
                             session_id: Optional[str] = None) -> Session: ...
    async def get_session(self, *, app_name: str, user_id: str,
                          session_id: str,
                          config: Optional[GetSessionConfig] = None) -> Optional[Session]: ...
    async def list_sessions(self, *, app_name: str,
                            user_id: str) -> ListSessionsResponse: ...
    async def delete_session(self, *, app_name: str, user_id: str,
                             session_id: str) -> None: ...
    async def append_event(self, session: Session, event: Event) -> Event: ...
```

`Session` 是 pydantic model,欄位:`id` / `app_name` / `user_id` / `state` / `events: list[Event]` / `last_update_time`。

**現有 `agent_messages` 表 schema**(`lib/db/models/agent_message.py`):
- `id`(autoincrement)、`sdk_session_id`(FK to `agent_sessions`)、`seq`、`payload: Text`(JSON 字串)、`created_at`/`updated_at`(來自 `TimestampMixin`)。
- **沒有 `message_type` 欄位**;訊息類型由 `payload` JSON 內 `type` 欄位區分(現有設計就是如此,跨 provider 共用)。

**選擇**:實作 `AgentMessagesSessionService(BaseSessionService)`,具體映射:

| ADK 方法 | 實作 |
|---|---|
| `create_session(*, app_name, user_id, state, session_id)` | 若 `session_id` 為 None,以 `build_external_session_id("gemini-full", uuid4().hex)` 產生;呼叫既有 `agent_session_repo.create()`(寫入 `agent_sessions` 表,以 `sdk_session_id=session_id`);回傳 `Session(id=session_id, app_name=app_name, user_id=user_id, state=state or {}, events=[])` |
| `get_session(*, app_name, user_id, session_id, config)` | 從 `agent_messages` 讀所有 `sdk_session_id=session_id` 的 row(按 `seq` 排序),把每筆 `payload` JSON 反序列化成 `Event`;回傳 `Session(id=session_id, app_name=app_name, user_id=user_id, state={}, events=[...])` |
| `list_sessions(*, app_name, user_id)` | 從 `agent_sessions` 表查所有屬於該 user 的 session,回傳 `ListSessionsResponse(sessions=[Session(...)])` 但**僅含 metadata**(不載入 events,效能考量) |
| `delete_session(*, app_name, user_id, session_id)` | 呼叫既有 `agent_session_repo.delete(session_id)`,FK CASCADE 自動清掉對應 `agent_messages` |
| `append_event(session, event)` 覆寫 | 呼叫 base class 預設(更新 `session.events` + state delta),再額外將 event 序列化為 JSON payload 寫入 `agent_messages`(下一個 `seq`) |

**`app_name` / `user_id` 的映射**:本專案無多租戶概念,`app_name="arcreel"`、`user_id` 取現有 session 所屬 project 名(`projects/<name>` 用於 audit/debug)。**這兩個欄位純粹滿足 ADK API,不影響業務邏輯**;從 `agent_messages` 讀回的 Session 一律用同樣的 `app_name`/`user_id` 重建。

**Event ↔ payload 序列化**:

ADK `Event` 是大型 pydantic model(20+ 欄位),包含 `content: types.Content`(parts[*] 含 text / function_call / function_response)、`partial`、`turn_complete`、`finish_reason`、`author`、`actions`、`id`、`timestamp` 等。

策略:`payload` 直接存 `event.model_dump_json(exclude_none=True)`,讀回時 `Event.model_validate_json(payload)`。優點:無損保留 ADK Event 全資訊;**但 payload schema 變成依賴 ADK 內部 model**,升 ADK 版本時若 Event schema 改了會破壞舊 session 重放。

**Mitigation**:`payload` 同時加一層 wrapper:

```json
{
  "kind": "adk_event",
  "adk_version": "1.32.0",
  "event": { ... event.model_dump_json output ... }
}
```

讀回時若 `adk_version` 與當前不符,先試 `Event.model_validate_json` 直接讀;失敗時 log warning 並回退到「降級重建」(把 event.content 的 parts 重組為純文字 `assistant` 訊息)。**舊 lite session 的 payload(`{"type": "text", "content": "..."}`等)結構不同**,讀寫時依 `kind` 欄位區分;沒有 `kind` 即視為 lite payload。

**替代方案**:

- 用 ADK 內建 `DatabaseSessionService`,建獨立 `adk_sessions` 表。**否決**:`agent_messages` 已是跨 provider 真相源(claude / gemini-lite / openai-lite 都用),分裂後舊 session 重放、列表查詢、統計都得雙寫。
- 不實作 `BaseSessionService`,改用 ADK 內建 `InMemorySessionService` + 在 provider 層手動把 events 雙寫到 `agent_messages`。**已重新評估後採納為 fallback**:若 spike 階段發現 `BaseSessionService` 的 `list_sessions`/`delete_session` 抽象與 `agent_session_repo` 的職責邊界對不齊,可改用 `InMemorySessionService`(SDK 內建,免實作) + provider 內 `_persist_event(event)` hook 雙寫。**Phase 1 day 4 必須做這個 go/no-go 決定**(見 task 2.7)。

**理由**:custom `BaseSessionService` 是「正規」整合路徑,但 ADK 1.32 抽象比預期複雜(4 個 abstract method、`Session` pydantic model、Event 結構大量 fields)。實作成本可能比預估的 ~250 行高 50%;若超過 ~400 行就改走 InMemorySessionService + 手動雙寫的 fallback,代價是 Runner 內部 session state 與 DB 不嚴格同步(對話中途崩潰可能丟最後幾個 events)。

### 4. `permission_gate` 透過 `before_tool_callback` 注入

**選擇**:在 `permission_gate.py` 新增 `as_adk_callback(gate: PermissionGate) -> Callable`:

```python
def as_adk_callback(gate):
    def callback(tool, args, tool_context):
        decision = gate.evaluate(tool_name=tool.name, args=args, ...)
        if decision.deny:
            # 回傳 dict → ADK 跳過 tool 執行並把 dict 當 tool result 回 LLM
            return {
                "permission_denied": True,
                "reason": decision.reason,
                "tool": tool.name,
            }
        return None  # 放行
    return callback
```

**替代方案**:

- 把 deny 拋 exception 讓 ADK 中斷對話。**否決**:與現狀語意不符,破壞「讓模型自適應、換路徑」的設計意圖(design.md line 81)。
- 在每個 `BaseTool.run_async()` 入口手動呼叫 `gate.evaluate()`。**否決**:分散在 7+ 個 tool 裡重複程式碼;`before_tool_callback` 是 ADK 提供的中心化攔截點,更內聚。

**理由**:`before_tool_callback` 回傳 dict 跳過執行的行為,與既有「deny → 包成 functionResponse 回模型」語意 1:1 對齊,且 hook 注入是 ADK 推薦模式。

### 5. Streaming 用 `Runner.run_async()` 事件流,不用 `Runner.run_live()`

**選擇**:`Runner.run_async()` 回傳 async iterator of `Event`,每個 event 投影到既有 SSE buffer(在 `adk_gemini_full_runtime_provider._project_to_sse()`)。

**替代方案**:

- `Runner.run_live()`(bidi streaming)。**否決**:v0.5.0 docs 標記 experimental,且目前 ArcReel 前端 SSE 是單向的,bidi 價值無法兌現。

**理由**:保守路徑,避免引入 experimental 特性導致回滾。

### 6. 直接切換,git revert 回滾

**選擇**:不引入 `ASSISTANT_GEMINI_FULL_BACKEND` 之類的 feature flag。Phase 2 直接 deploy ADK 版本到 staging,7 天觀察期透過監控 SSE 錯誤率、`agent_messages` 寫入異常與 tool_result payload 結構決定是否進 production;有 P1 問題則 revert commit + redeploy。

**替代方案**:

- 三階段 env var(`legacy` → `adk` 預設 → 純 `adk`)。**否決**:env var 把實作細節暴露給運維/使用者(該選哪個?何時切?),違反「實作切換不該變成使用者設定」原則;且 git revert + redeploy 的回滾速度與 env var flip 在 docker compose 環境下差距不大。

**理由**:registry 註冊單一 provider 程式碼簡潔(無 if/else 分支);出事 revert 提交即恢復舊行為,不留可疑的「第二實作路徑」誘導後續開發者依賴 fallback。

## Risks / Trade-offs

- **[Risk] 7 skill schema adapter 比現狀還囉嗦** → Phase 1 spike 第 3 天就要做 LOC 對比;若 `SkillBaseTool` 實作 + 7 instance 總 LOC > 現有 `_dispatch_function_call` + `SKILL_DECLARATIONS` 維護成本,**取消整個遷移**。Phase 1 是 go/no-go 檢查點,不是「先做完再決定」。

- **[Risk] `google-adk` breaking change 頻率高(雙週發版)** → Mitigation:(a) `pyproject.toml` 鎖 minor 版本(`google-adk>=1.32,<1.33`),不允許 `^`;(b) 新建 `docs/adk-upgrade-checklist.md` 記錄每次升版的回歸測試清單;(c) CI 加 ADK 版本探針,新版釋出時跑現有測試預警。

- **[Risk] `BaseSessionService` 邊界 case 沒覆蓋** → ADK Event 類型可能比目前已知(text / function_call / function_response / thinking)多。Mitigation:Phase 1 spike 要觸發所有可能的 event path(含 parallel function call、tool error、interrupt),確認全部能映射;不能映射的擴展 `agent_messages.message_type` 列舉,加 migration。

- **[Risk] 效能回歸** → ADK Runner 多一層抽象,理論上可能比手刻慢 50–200ms/turn。Mitigation:Phase 1 spike 跑 10 次 generate-script 工作流,對比遷移前後 P50 / P95 延遲;超過 +20% 視為不可接受,需調優或取消。

- **[Trade-off] 新增 `google-adk` 依賴(含 `opentelemetry-*`、`google-cloud-aiplatform` 等傳遞依賴)** → 映像體積可能增長 30–60 MB,啟動時間可能 +0.5–1s。**接受**:與回收 ~300 行程式碼 + 享受 ADK 維護紅利的收益相比可接受;運維監控指標裡增加映像大小預警。

- **[Trade-off] 學習曲線** → 後續維護此 provider 的工程師需熟悉 ADK API;目前團隊對 `google-genai` 原生 API 更熟。**接受**:ADK 文件充足,且 ADK 抽象與 `claude_agent_sdk` 相似,團隊已有 SDK 模型經驗。

## Migration Plan

**Phase 0:準備(1 天)**

1. `pyproject.toml` 加 `google-adk>=1.32,<1.33` 依賴;`uv sync` 驗證安裝與傳遞依賴。
2. 跑現有 `tests/test_gemini_full_runtime.py` 取得目前 baseline(必須 80+ 全綠)。

**Phase 1:spike(2 週)**

3. 實作 `adk_session_service.py` + 單元測試,覆蓋所有 ADK Event 類型映射。
4. 實作 `adk_tool_adapters.py` 的 `SkillBaseTool` 泛型類 + 7 個 skill instance。**Day 3 LOC checkpoint**:若超過 150 LOC,go/no-go review。
5. 實作 `permission_gate.as_adk_callback()` + 單元測試。
6. 實作 `adk_gemini_full_runtime_provider.py`:組裝 `Agent` + `Runner` + custom session service + before_tool_callback + tool list;實作 `_project_to_sse()` 把 ADK Event 投到既有 SSE buffer。
7. `service.py` 直接在 `runtime_provider_registry` 註冊 `AdkGeminiFullRuntimeProvider` 取代 legacy provider(無 env var、無 if/else)。
8. 移植 `test_gemini_full_runtime.py` 核心案例到 `tests/test_adk_gemini_full_runtime.py`;spike 期間兩套測試並行驗證一致性。
9. spike 末測:`gemini_full_smoketest.py` 跑 10 輪真實 generate-script 工作流,對比延遲、token 用量、行為一致性。

**Phase 2:staging 觀察(1 週)**

10. deploy 到 staging 環境,監控 SSE 錯誤率、`agent_messages` 寫入異常、`tool_result` payload 結構;不允許進 production 直到 7 天無 P1。
11. 任何 P1 問題:revert commit + redeploy,回到 Phase 1 除錯。

**Phase 3:cleanup(1 天)**

12. 確認 staging 觀察期 7 天無 P1 問題。
13. 刪除 `server/agent_runtime/gemini_full_runtime_provider.py` 與 `tests/test_gemini_full_runtime.py`(本變更已直接執行)。
14. 更新 `CLAUDE.md` 中 `agent_runtime/` 模組清單,移除 `gemini_full_runtime_provider.py`,註明 `adk_gemini_full_runtime_provider.py` 基於 google-adk。
15. CHANGELOG 記錄遷移完成。

**回滾策略**

- 任何階段出 P1:revert 對應 commit,重新 deploy。直接切換 + revert 路徑簡單,程式碼裡沒有「第二實作」誘導後續維護者依賴 fallback。

## Open Questions

- 是否要在本變更內順便重構 `permission_gate` 的 policy 表達(目前 hard-coded 在程式碼裡)?**暫不**,留待後續變更。
- ADK 提供 OpenTelemetry tracing 是否要接到專案既有的觀測系統?**Phase 2 結束後評估**,目前先用 ADK 預設 stdout exporter 觀察。
