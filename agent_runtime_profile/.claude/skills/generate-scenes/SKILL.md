---
name: generate-scenes
description: 新增場景定義到專案。當使用者說"生成場景"、"新增場景"、"整理場景設定"、或需要為劇本補充場景環境定義時使用。把場景的名稱與敘事式描述寫入 project.json.scenes。
---

# 新增場景定義

把場景定義寫入 `project.json.scenes`。此工具只同步**文字後設資料**
(場景名稱 + 描述),不立即生成圖片;圖片生成由後續分鏡流程處理。

## 工具

`generate_scenes` — 向 `project.json` 新增一組場景定義。

參數:

- `scenes`(必填,陣列):每個元素為物件,含
  - `name`(必填字串):場景名稱
  - `description`(必填字串):敘事式描述

## 場景描述編寫指南

編寫 `description` 時使用**敘事式寫法**,不要羅列關鍵詞。涵蓋場景環境、
氣氛、時間、地點、主要景物。

**示例**:
> "黃昏時分的江南庭院,青石板鋪就的小徑蜿蜒穿過。庭中一棵老梅樹枝幹虯曲,
> 幾點殘雪未消。迴廊朱漆斑駁,簷下掛著一盞褪色的紅燈籠,在晚風中輕輕搖晃。"

## 工作流程

1. 從原文或使用者描述整理出需要的場景。
2. 為每個場景寫敘事式 `description`。
3. 發出 `generate_scenes` function call,帶上 `scenes` 陣列。
4. 檢查回傳的 `ok` 欄位。`ok: false` 代表未寫入,依 `reason` 修正後重試,
   **不可回報「已完成」**。

> ⚠️ **嚴禁用 `fs_write` 改 `project.json`。** 沙盒會拒絕並回
> `error: "use_dedicated_tool"`,看到此錯誤代表選錯工具,改用 `generate_scenes`。
