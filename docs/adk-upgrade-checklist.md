# google-adk Upgrade Checklist

每次升級 `google-adk` 版本時，請務必執行以下回歸測試清單，以確保 Agent 運行時的穩定性與向後相容性。

## 1. 核心依賴驗證
- [ ] 執行 `uv sync` 確認升級後的 `google-adk` 版本與既有依賴 (例如 `google-genai`, `pydantic`) 沒有衝突。
- [ ] 檢查 `pyproject.toml` 中的版本鎖定是否更新正確。

## 2. 單元測試回歸
- [ ] 執行 `uv run python -m pytest tests/test_gemini_full_runtime.py -v`，確保核心 Provider 功能全部通過。
- [ ] 執行 `uv run python -m pytest tests/test_adk_session_service.py -v`，確保 Session Service 橋接邏輯正常。
- [ ] 執行 `uv run python -m pytest tests/test_adk_tool_adapters.py -v`，確保 Skill Tool Adapaters 註冊與 dispatch 正常。
- [ ] 執行整體測試 `uv run python -m pytest -v`，確認無其他連帶影響。

## 3. 功能一致性驗證
- [ ] 確保 `_get_declaration()` 產生的 FunctionDeclaration 與 `SKILL_DECLARATIONS` bit-for-bit 一致。
- [ ] 驗證 SSE Event Stream (text deltas, tool_use, tool_result) 結構未發生變化。
- [ ] 驗證 Permission Gate (Hook) Deny 時，依然回傳 dict 且能正確落為 `tool_result`，而非中斷對話。

## 4. Smoketest (端對端驗證)
- [ ] 執行 `scripts/gemini_full_smoketest.py` 進行 generate-script 等完整工作流測試。
- [ ] 觀察並記錄升級前後的 P50 / P95 延遲，確保無明顯的效能退化 (>20%)。
- [ ] 確認 Token 用量統計無異常變化。

## 5. 觀察與部署
- [ ] 部署至 Staging 環境，觀察 24 小時內的 SSE 錯誤率與 `agent_messages` 寫入異常率。
- [ ] 若無 P1 級別錯誤，才考慮更新正式環境的版本。
