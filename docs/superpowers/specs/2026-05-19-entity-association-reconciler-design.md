# 實體關聯補齊（Entity Association Reconciler）設計

- 狀態：Draft
- 日期：2026-05-19

## 問題

高亮與片段資產顯示依賴結構化關聯欄位（`characters_in_segment` / `clues_in_segment` /
`scene_in_segment`），但這些欄位由 AI 生成、不可靠。AI 經常在正文（`novel_text`、
`image_prompt.scene`、`video_prompt.action`）寫到某角色／道具／場景，卻沒同步填進關聯欄位。
前端只看關聯欄位，結果不高亮、片段 header 也不顯示該資產 ——「AI 有寫到，但系統沒認出來」。

確認過生成 prompt（`lib/prompt_builders_script.py`）：AI 被要求填結構欄位、正文寫**裸名**
（無 `@`）。`@` 只是使用者手動輸入時的標記語法，不是 AI 生成階段的產物。

根因不是顏色或 `@` 顯示，而是**生成後缺少一個 deterministic 的關聯補齊步驟**。

## 解法（途徑 B）

劇本儲存時跑一個 deterministic reconciler，掃描三處正文，用 project.json 已知名稱
（含括號別名拆解）做 longest-first 非重疊子字串比對，**只新增缺漏**到結構欄位，
絕不移除 AI 已填的。前端高亮改用結構欄位當名稱來源，套同一份比對規格。

選途徑 B 而非「純讀時計算」或「改 AI prompt」：B 同時滿足 deterministic（不靠 AI）
與 union 安全（不破壞 AI 已對的部分），且真正關掉前端高亮缺口。

## §1 比對規格（前後端唯一真相）

- **名稱來源**：project.json `characters` / `clues` / `scenes` 的 key。`scenes` 可能為
  `None`，視為空。
- **別名拆解**：正則 `^(.+?)\s*[（(]\s*(.+?)\s*[）)]\s*$`（全半形括號皆收，只處理一層）。
  匹配 → `[完整key, group1, group2]`，去空白去重；不匹配 → `[name]`。
- **比對演算法**：所有比對詞合併，按長度由長到短排序；同長度以 kind 優先序
  `character > clue > scene` 打平手。逐字元掃描，命中最長比對詞 → 記錄原始 key、
  游標前進命中長度（非重疊）；未命中 → 游標 +1。
- **ASCII 詞邊界**：純 ASCII 比對詞需做 word boundary 檢查（前後不可為 ASCII word
  char），避免 `Hero` 命中 `Heroic`；CJK 不做邊界檢查。
- **掃描範圍**（reconciler）：`novel_text`、`image_prompt.scene`、`video_prompt.action`
  逐欄掃描後 union。
- **字元計量**：前後端必須以相同單位前進游標（見 §6）。

實作現況：`lib/entity_matching.py` 與 `frontend/src/utils/entity-matching.ts` 已依此
規格對稱實作完成（含別名拆解、kind 優先序、ASCII 邊界）。

## §2 後端 reconciler 模組

新檔 `lib/entity_reconciler.py`，純函式、immutable（回傳新 dict，不 mutate 入參）：

- `reconcile_segment(segment, characters, clues, scenes, *, fields) -> dict`
  - 掃 `novel_text` / `image_prompt.scene` / `video_prompt.action`，呼叫
    `entity_matching.scan_entity_mentions`。
  - `characters_in_*` / `clues_in_*` = `unique(原有 + 命中)`（**union，只補不刪**）。
  - `scene_in_*`：**僅在現值為空時**填掃描命中的第一個 scene key；已有值不覆寫。
- `reconcile_script(script, project_json) -> dict`
  - narration → 走 `segments` + `*_in_segment` 欄位；drama → `scenes` + `*_in_scene`。
  - 回傳新 script dict。

## §3 接入 save_script

`ProjectManager.save_script` 在 content_mode 分流前插入：

```python
try:
    project_json = self.load_project(project_name)
    script = reconcile_script(script, project_json)
except Exception:
    logger.warning(..., exc_info=True)  # 補齊非關鍵路徑，失敗不阻擋存檔
```

- 涵蓋所有寫入路徑（AI 生成、手動編輯、匯入）。
- `load_project` 失敗或無 characters → reconciler 收空集，等同 no-op。
- reconciler 為純函式，在 save_script 內以重新賦值方式接入，不擴散既有 mutation。

## §4 前端高亮改結構欄位驅動

現況已完成：`tokenizeForHighlight` 支援 `linkedNames`，`findPlainMentionAt` +
`isPlainMentionBoundary` 提供無 `@` 裸名比對，scene 維度全鏈路打通，`@` 手動輸入路徑
保留不動。

待補：前端高亮的別名比對改用 `entity-matching.ts` 的 `scanEntityMentions`／
`expandEntityAliases`，與後端共用 §1 規格（目前 highlight 仍比對完整 key，未拆別名）。

## §5 共用測試向量

新增一份 JSON 向量（`[{text, characters, clues, scenes, expected}]`），Python 測試與
TS 測試各讀同一份跑。任一端行為漂移即測試紅。補 CJK／星平面字（emoji）邊界案例。

## §6 UTF-16 vs code point 邊界

Python 以 code point 計、TS `String.length` 以 UTF-16 code unit 計。名稱含星平面字
（emoji 道具名）時游標前進量不同 → 前後端命中漂移。需讓兩端對星平面字的前進量一致
（TS 端以 code point 迭代，或 Python 端對齊 UTF-16）。由 §5 共用向量的 emoji 案例守住。

## 測試策略

- `entity_matching` / `entity-matching`：既有單元測試 + §5 共用向量。
- `entity_reconciler`：union 不刪、scene 只在空時補、narration/drama 分流、空
  project.json no-op、immutable（入參不被 mutate）。
- `save_script` 接入：reconcile 失敗不阻擋存檔。

## 範圍外

- 不改 AI 生成 prompt。
- 不在正文加 `@`（正文不動，只補結構欄位）。
- 不重構 save_script 既有 mutation 模式。
- `entity-mentions.ts` 既有 `@` 手動輸入路徑不動。
- `AddSceneForm.tsx` 的 `React.FormEvent` deprecation 為既有技術債，與本任務無關。
