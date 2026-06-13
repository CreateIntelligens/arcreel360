# 助手工具審批流改造建議（問題1）

## 背景

當前 `can_use_tool` 僅對 `AskUserQuestion` 走使用者互動，其餘工具預設 `allow`。
這會讓 Web 端失去對高風險工具呼叫（如 `Bash`、`Write`、`Edit`）的可見性與控制能力，不符合官方關於“應用側承接審批請求並返回決策”的推薦實踐。

## 目標

1. 所有非自動放行工具請求都能在前端展示為“待審批”。
2. 使用者可執行 `允許 / 拒絕 / 允許並修改引數` 三類決策。
3. 決策結果迴流到 `can_use_tool`，不中斷當前流式會話。
4. 審批請求可重連恢復（頁面重新整理或 SSE 重連後不丟審批狀態）。

## 建議架構

## 1) 事件模型統一

新增一種執行時訊息（建議）：

- `tool_approval_request`
  - `request_id`
  - `tool_name`
  - `input`
  - `created_at`
  - `session_id`
  - `risk_level`（可選，前端分級展示）

前端 SSE 新增事件（建議）：

- `approval`：承載 `tool_approval_request`

> 也可複用 `question` 事件通道，但建議獨立事件型別，避免 `AskUserQuestion` 與工具審批語義混淆。

## 2) SessionManager 側改造

在 `_build_can_use_tool_callback` 中：

1. 識別 `AskUserQuestion`（保持現有邏輯）。
2. 對其他工具：
   - 若命中“自動放行規則”則直接 `PermissionResultAllow`。
   - 否則建立 `pending_approval`，向訊息緩衝區寫入 `tool_approval_request`，並 `await` 使用者決策。
3. 使用者決策返回後：
   - `allow` -> `PermissionResultAllow(updated_input=...)`
   - `deny` -> `PermissionResultDeny(message=..., interrupt=...)`

新增 `ManagedSession.pending_approvals` 與對應：

- `add_pending_approval()`
- `resolve_pending_approval()`
- `cancel_pending_approvals()`
- `get_pending_approval_payloads()`

## 3) AssistantService / Snapshot 側

`snapshot` 返回中新增：

- `pending_approvals: []`

SSE 重連首包 `snapshot` 應包含未決審批項，確保前端可恢復審批 UI。

## 4) Router 側

新增介面（建議）：

- `POST /api/v1/assistant/sessions/{id}/approvals/{request_id}/decision`
  - 請求體：
    - `decision`: `allow | deny`
    - `updated_input`（可選）
    - `message`（拒絕原因，可選）
    - `interrupt`（可選）

## 5) 前端側

`use-assistant-state` 新增：

- `assistantPendingApproval`
- `assistantApproving`
- `handleApproveToolRequest(requestId, decisionPayload)`

`AssistantMessageArea` 增加審批卡片區：

1. 顯示工具名、關鍵引數摘要、風險標記。
2. 支援允許/拒絕。
3. 支援高階模式編輯 `updated_input`（JSON）。

## 預設策略建議

預設自動放行（可配置）：

- `Read`
- `Glob`
- `Grep`
- `LS`

預設需審批：

- `Bash`
- `Write`
- `Edit`
- `MultiEdit`
- 其他具副作用或外部訪問能力工具

## 相容與遷移

1. 第一階段：後端先支援 `pending_approvals` 與 decision API，前端灰度接入。
2. 第二階段：關閉“非 AskUserQuestion 全量預設放行”。
3. 第三階段：加入規則配置（專案級 / 會話級）。

## 驗收清單

1. 觸發 `Bash` 時，前端出現審批卡片而非靜默執行。
2. 點選“拒絕”後，模型收到拒絕反饋並繼續後續推理。
3. 重新整理頁面後，未處理審批仍能在 `snapshot.pending_approvals` 恢復。
4. 流式會話不中斷，`status` 事件仍按 `ResultMessage` 收斂。
5. `AskUserQuestion` 流程不迴歸。
