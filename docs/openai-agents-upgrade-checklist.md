# OpenAI Agents SDK 升級檢查清單

本檢查清單用於升級 `openai-agents` 版本時確認 `openai-full` runtime 仍符合 ArcReel 的工具循環、權限閘門與 session 持久化契約。

## 升級前

- [ ] 閱讀 OpenAI Agents SDK release notes，確認 `Agent`、`Runner.run_streamed()`、`FunctionTool`、stream event 型別與 `session` 參數是否有 breaking change。
- [ ] 確認 `pyproject.toml` 的版本範圍仍鎖定在已驗證 minor 版本。
- [ ] 確認 `openai-agents` 與既有 `openai` SDK 版本可同時解析。

## 必跑回歸

```bash
uv sync
uv run ruff check .
uv run python -m pytest tests/test_assistant_*.py -v
uv run python -m pytest tests/test_openai_tool_adapters.py tests/test_permission_gate.py tests/test_openai_full_runtime.py -v
uv run python -m pytest tests/test_session_identity_*.py tests/test_assistant_service_*.py -v
```

前端若本機未安裝 `pnpm`，改用 `frontend-builder` 容器執行：

```bash
POSTGRES_PASSWORD=testpass docker compose run --rm --entrypoint /bin/sh frontend-builder -c 'set -e; mkdir -p /tmp/bin /tmp/.corepack /tmp/.npm /tmp/.pnpm; export PATH="/tmp/.pnpm:/tmp/bin:$PATH"; corepack enable --install-directory /tmp/bin; corepack prepare pnpm@latest --activate; node_modules/.bin/tsc --noEmit -p .'
```

## 行為檢查

- [ ] `Runner.run_streamed()` 呼叫仍明確傳入 `session=None`。
- [ ] `FunctionTool.params_json_schema` 仍接受 `_gemini_to_openai_schema()` 產出的 strict JSON Schema。
- [ ] `permission_gate.as_openai_wrapper()` deny 時不執行 handler，回傳 `{"permission_denied": true, "reason": ..., "tool": ...}`。
- [ ] `tool_use` / `tool_result` / `assistant` 訊息仍寫入 `agent_messages`，且可被歷史重放。
- [ ] `openai-full:` session id 仍由 `infer_provider_id()` 路由到 `openai-full`，`openai:` 仍路由到 `openai-lite`。
- [ ] `/settings` 中 OpenAI × 工作流模式仍可選，且 capability banner 不顯示降級提示。

## 真實供應商 smoke test

- [ ] 使用測試 OpenAI API key 建立 `openai-full` session。
- [ ] 觸發一次 `generate_script` tool call，確認 args 結構與既有 Gemini tool schema 對齊。
- [ ] 觸發一次 permission deny scenario，確認 SSE 與 `agent_messages` 中的 `tool_result` payload 與 `gemini-full` 對齊。
- [ ] 執行一次最小漫畫工作流 smoke test，至少涵蓋 `generate-script` 與 `generate-storyboard`。

## 升級紀錄

每次升級後在 PR 或 changelog 中記錄：

- 舊版本與新版本。
- 是否有 SDK API 變更。
- 上述回歸與 smoke test 結果。
- 若跳過真實供應商測試，需記錄原因與補測時間。
