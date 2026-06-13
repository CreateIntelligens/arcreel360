# 已知問題

多供應商影片生成接入（#98）過程中發現的存量技術債，不影響功能正確性，記錄以便後續迭代。

---

## ~~1. UsageRepository 費用路由邏輯洩漏~~ ✅ 已修復

**修復：** `CostCalculator.calculate_cost()` 統一入口按 `(call_type, provider)` 顯式路由，Repository 只調一次。Gemini video 不再隱式 fallthrough。

---

## ~~2. CostCalculator 費用結構不對稱~~ ✅ 已修復

**修復：** 隨 Issue 1 一併解決。`calculate_cost()` 統一入口隱藏了各供應商的費率字典結構差異。

---

## 3. VideoGenerationRequest 引數膨脹

**位置：** `lib/video_backends/base.py` — `VideoGenerationRequest`

**現狀：** 共享 dataclass 中混入了後端特有欄位（`negative_prompt` 為 Veo 特有，`service_tier`/`seed` 為 Seedance 特有），靠註釋"各 Backend 忽略不支援的欄位"約定。

**評估：** 僅 3 個後端 3 個特有欄位，引入 per-backend config 類的複雜度不值得。待第 4 個後端接入時再重構。

---

## ~~4. SystemConfigManager secret 塊重複模式~~ ✅ 已修復

**修復：** 將 `_apply_to_env()` 中 ~8 個相同模式的 if/else secret 塊替換為元組 + 迴圈。

---

## 5. UsageRepository finish_call 雙次 DB 往返

**位置：** `lib/db/repositories/usage_repo.py` — `finish_call()`

**現狀：** 先 `SELECT` 讀取整行（取 `provider`、`call_type` 等欄位計算費用），再 `UPDATE` 寫回結果。對每個任務兩次序列資料庫往返。

**評估：** 影片生成耗時分鐘級，DB 往返影響極小。消除需改動 3 個呼叫方（MediaGenerator、TextGenerator、UsageTracker），風險不對稱。

---

## 6. UsageRepository.finish_call() 引數膨脹

**位置：** `lib/db/repositories/usage_repo.py` — `finish_call()`，`lib/usage_tracker.py` — `finish_call()`

**現狀：** `finish_call()` 已有 9 個 keyword 引數，且 `UsageTracker.finish_call()` 1:1 映象透傳。

**評估：** 與 Issue 5 耦合，單獨改收益低。待 Issue 5 一併重構。

---

## ~~7. call_type 裸字串缺乏型別約束~~ ✅ 已修復

**修復：** Python 端定義 `CallType = Literal["image", "video", "text"]`（`lib/providers.py`），前端定義對應 `CallType` 型別（`frontend/src/types/provider.ts`），在介面簽名中統一使用。

---

## ~~8. UsageRepository 查詢方法 filter 構建重複~~ ✅ 已修復

**修復：** 將 `_base_filters()` 提升為類方法 `_build_filters()`，三個查詢方法共享。

---

## ~~9. update_project 後端欄位缺少 provider 合法性校驗~~ ✅ 已修復

**修復：** 提取共享校驗函式 `validate_backend_value()`（`server/routers/_validators.py`），`update_project()` 和 `patch_system_config()` 共同使用，拒絕非法 provider/model 值並返回 400。

---

## ~~10. test_text_backends 測試檔案 asyncio.to_thread patch 重複~~ ✅ 已修復

**修復：** 在 `tests/test_text_backends/conftest.py` 中提取 `sync_to_thread` fixture，各測試檔案共享。
