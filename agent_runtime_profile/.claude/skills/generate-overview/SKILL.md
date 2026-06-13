---
name: generate-overview
description: 生成或更新專案世界觀/概述。當使用者說"生成世界觀"、"寫入世界觀"、"生成概述"、"整理故事設定"、或專案進度卡在「專案概述」時使用。把 synopsis/genre/theme/world_setting 結構化寫入 project.json。
---

# 生成專案世界觀/概述

把專案的世界觀整理成結構化資料寫入 `project.json.overview`，包含
`synopsis`(故事梗概)、`genre`(題材類型)、`theme`(核心主題)、
`world_setting`(世界觀與時代背景設定)四個欄位。專案必須有結構化 overview，
製作流程才會從「專案概述」推進到「角色場景」階段。

> 🔴 **鋼定規則 — 違反即視為任務失敗:**
>
> 「生成世界觀」「寫入世界觀」是**工具呼叫任務**,不是寫作任務。把世界觀內容
> 打在回覆裡給使用者看 **不算完成**——必須實際發出 function call。

## 兩個工具

| tool | 用途 |
|------|------|
| `generate_overview` | 讀取 `source/` 原文,自動生成並儲存完整概述 |
| `update_overview` | 把已在對話中整理好的欄位寫入 `project.json.overview` |

### generate_overview — 從原文自動生成

無參數。讀 `source/` 原文 → 生成 synopsis/genre/theme/world_setting →
直接寫入 `project.json`。適合「請根據原文生成世界觀」這類請求。

### update_overview — 寫入已整理好的內容

當你已在對話中產出世界觀(例如使用者口述、或你先讀原文整理),用此工具保存。
參數皆為選填字串,至少需一個非空:

- `synopsis` — 故事梗概
- `genre` — 題材類型
- `theme` — 核心主題
- `world_setting` — 世界觀與時代背景設定

## 工作流程

1. 判斷來源:有原文且使用者要自動生成 → `generate_overview`;
   已有整理好的內容 → `update_overview`。
2. 發出對應 function call。
3. 檢查回傳的 `ok` 欄位。`ok: false` 代表未寫入,依 `reason` 修正後重試,
   **不可回報「已完成」**。
4. 看到 `ok: true` 才回覆使用者「世界觀已寫入,專案進度已推進」。

> ⚠️ **嚴禁用 `fs_write` 改 `project.json`。** 沙盒會拒絕並回
> `error: "use_dedicated_tool"`,看到此錯誤代表選錯工具,改用 `update_overview`。
