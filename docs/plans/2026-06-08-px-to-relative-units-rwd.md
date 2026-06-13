# 計畫：固定布局尺寸 px → 相對單位（RWD 準備）

**狀態：Draft**
**範圍：僅「固定布局尺寸」的 px → `rem` / `%` / `flex` / viewport units。不動字級、不動視覺細節、不動 hairline border。**
**前置盤點：本計畫附帶完整清單，執行者不需再自行搜尋（但需照「驗證」節重新確認行號未漂移）。**

---

## 0. 背景與目標

專案偏好相對單位（見 `~/.claude/CLAUDE.md` 全域規則「Frontend」節）。重點摘錄，**執行時必須遵守**：

> - **Avoid `px` units.** 用相對單位：`rem`/`em`(尺寸/間距/字級)、`%`(比例布局)、viewport units(`dvh`/`svh`/`vw`)。
> - Hairline border(`1px`)等次像素細節是可接受例外。
> - **優先彈性尺寸(`%`/`flex`/viewport)勝過固定 `rem`** — 寬與高皆然。固定尺寸加總超過容器會逼出捲軸。
>   - 寬：彈性欄位用 `%`；固定 `rem` 只留給真正固定的件(icon/checkbox/列號/按鈕/頭像)。
>   - 高：優先 `flex:1`/`%`/`dvh`；固定 `rem` 高只留給工具列、單行列。
>   - **避免容器上的 `min-width`/`min-height`**，除非有實際理由 — 它們是非預期捲軸的常見成因。

**本計畫只處理「真正影響 RWD 的固定布局尺寸」**，共 **9 個 className 站點 / 6 個檔案**。已盤點確認：字級 `text-[10px]/[11px]`（106 處）屬 a11y 範疇、**不在本計畫範圍**；CSS 的 `blur()`/`shadow`/裝飾性 orb（`380px/320px`）/scrollbar `4px`/border `1-3px` 皆為視覺細節，**保留不動**。內聯 `style={{...px}}` 經盤點為 0 處布局尺寸。

**非目標**：不要順手改字級；不要改視覺效果；不要為了「消滅 px」而把可接受例外也換掉；不要改動本清單以外的檔案。

---

## 1. 待改清單（逐項：檔案、行、現值、建議、理由）

> Tailwind 換算：`1rem = 16px`。`w-[90px]→w-[5.625rem]`、`120px→7.5rem`、`140px→8.75rem`、`400px→25rem`、`560px→35rem`、`120px(max-w)→7.5rem`。
> 凡 `rem` 是「保持固定尺寸但跟隨根字級」；凡 `%`/`flex`/`vh` 是「真正彈性」。下方已標明每處該用哪種。

### 1.1 縮圖（保持固定比例，換 `rem` — 屬規則允許的「頭像/縮圖」例外，但仍去 px）

這兩個檔是同一個 2:3 縮圖樣式（角色 / 線索）。`shrink-0` 已防壓縮，尺寸本就該固定，只是改用 `rem` 跟隨字級。

- **`src/components/ui/AvatarStack.tsx:46`**
  現值：`className="h-[120px] w-[90px] shrink-0 rounded object-cover"`
  改為：`className="h-[7.5rem] w-[5.625rem] shrink-0 rounded object-cover"`
- **`src/components/ui/AvatarStack.tsx:49`**
  現值：`className="flex h-[120px] w-[90px] shrink-0 items-center justify-center rounded bg-gray-800"`
  改為：把 `h-[120px] w-[90px]` → `h-[7.5rem] w-[5.625rem]`，其餘不動。
- **`src/components/ui/ClueStack.tsx:45`** — 同上，`h-[120px] w-[90px]` → `h-[7.5rem] w-[5.625rem]`。
- **`src/components/ui/ClueStack.tsx:48`** — 同上。

> 注意：AvatarStack 與 ClueStack 縮圖尺寸目前一致。若要徹底去重可抽共用 class 常數，但**本計畫不做抽取**（屬另一個 /simplify 任務），僅就地換單位。

### 1.2 文字區最小高度（去 `min-height`，改 viewport 相對 + 可拉伸）

- **`src/components/canvas/timeline/PreprocessingView.tsx:160`**
  現值：`className="min-h-[400px] w-full resize-y rounded-lg border border-gray-700 bg-gray-800 p-4 font-mono text-sm leading-relaxed text-gray-200 outline-none focus-ring focus-visible:border-indigo-500"`
  建議：`min-h-[400px]` → `min-h-[50dvh]`（半個視口高，隨螢幕縮放；`resize-y` 仍可手動拉伸）。
  理由：規則明文「避免容器 `min-height`」，且固定 25rem 在矮視窗會撐出捲軸。若團隊覺得 `50dvh` 在超寬螢幕太高，退而求其次用 `min-h-[25rem]`（至少跟隨字級）——**首選 `50dvh`**。

### 1.3 容器 `min-width`（規則點名的捲軸成因）

- **`src/components/ui/DropdownPill.tsx:47`**
  現值：`width="min-w-[140px]"`（傳給 `Popover` 的 `width` prop）
  改為：`width="min-w-[8.75rem]"`
  理由：popover 寬度下限，換 `rem` 跟隨字級。此處 `min-w` 有實際理由（避免選單過窄），保留語意、僅換單位。
- **`src/components/pages/agent-config/AssistantRuntimeGrid.tsx:48`**
  現值：`className="grid min-w-[560px] grid-cols-[8rem_repeat(3,minmax(7.5rem,1fr))] text-sm"`
  改為：`min-w-[560px]` → `min-w-[35rem]`（grid 軌道已是 `rem`/`fr`，下限統一成 `rem` 跟隨字級；此表格本就需要水平捲動，`min-w` 是刻意的——僅換單位，不移除）。
  **注意**：此處 `min-w` 是刻意讓窄螢幕水平捲動的設計，**不要改成 `%` 或移除**，只換單位。

### 1.4 數字輸入框 max-width（低風險，換 `rem`）

- **`src/components/pages/agent-config/AdvancedSettingsSection.tsx:39`**
  現值：``className={`${inputClassName} mt-1.5 max-w-[120px]`}``
  改為：`max-w-[120px]` → `max-w-[7.5rem]`
- **`src/components/pages/agent-config/AdvancedSettingsSection.tsx:56`** — 同上 `max-w-[120px]` → `max-w-[7.5rem]`。
  理由：限制 number input 寬度的固定上限，換 `rem` 即可，不需彈性。

---

## 2. 明確「保留不動」清單（避免執行者誤改）

- **字級**：所有 `text-[10px]` / `text-[11px]`（共 106 處）——不在本計畫，**不要動**。
- **視覺效果**：`blur(14px/16px/18px/40px)`、`box-shadow ...px`、`background-size 28px/96px`、`translateY(±Npx)`、`@keyframes` 內位移——**保留**。
- **裝飾性元素**：`app.css` 的 `.landing-orb-a/.landing-orb-b`（`380px/320px`）——模糊光斑裝飾，**保留**。
- **scrollbar**：`styles.css` `::-webkit-scrollbar { width/height: 4px }`——視覺細節，**保留**。
- **border / hairline**：所有 `1px`/`2px`/`3px` border、`border-left: 3px`——規則允許的例外，**保留**。
- **media query 斷點**：`@media (max-width: 1024px/640px)`——斷點本來就用 px，**保留**。
- **Tailwind 內建 spacing class**（`gap-2`/`p-4`/`h-8`/`w-28`/`mt-1.5` 等具名 class）——這些底層已是 `rem`，**不是 px，不要動**。

---

## 3. 執行步驟

1. 逐項套用第 1 節的 9 個替換（6 個檔案）。每處只改尺寸 token，不動同一 className 內其他 class。
2. 不新增、不刪除檔案；不抽共用（縮圖去重屬另案）。
3. 改完後逐檔自查：該行其餘 class 是否原封不動。

---

## 4. 驗證（執行者必跑，貼出結果）

> 已盤點：本計畫 6 個檔案**皆無對應的 `*.test.tsx`**，且唯二間接觸及的測試
> （`TimelineCanvas.test.tsx`、`SegmentCard.test.tsx`，經 `PreprocessingView`）**未斷言**任何被改的 px 值。
> 因此不需逐檔指定測試，跑全套即可。

```bash
cd frontend

# a. 型別檢查（不得新增錯誤）
pnpm typecheck

# b. 全套前端測試 + typecheck（pnpm check = typecheck + test）
pnpm check 2>&1 | tail -20
```

驗證通過標準：
- `pnpm typecheck` 無新錯誤。
- `pnpm check` 全綠。**若**意外有測試斷言了舊 px 字串（盤點時未發現，但行號可能漂移），同步改為新 `rem`/`dvh` 值——這是預期的、合理的測試更新，不是回歸。
- 視覺上 1.2 的 textarea 在矮視窗不再溢出（人工或截圖確認，可選）。

---

## 5. 風險與注意

- **測試斷言**：本專案部分 layout 測試會 `toHaveClass("...")` 斷言尺寸 class（例如 lorebook/EpisodeActionsBar 的測試模式）。盤點時本計畫 6 檔的被改 px 值**未被任何測試斷言**，故預期 `pnpm check` 直接通過；但若行號漂移後發現有斷言，**必須同步更新斷言**——這是計畫的一部分，不是回歸。
- **`1.2` 的 `50dvh` 決策**：若團隊偏好維持固定高度語意，可改用 `min-h-[25rem]`。預設採 `50dvh`（更符合 RWD 規則）。
- **不要擴大範圍**：看到附近其他 px（字級、陰影）不要順手改——超出本計畫即視為越界。
- **Tailwind 任意值語法**：`rem` 小數要用方括號任意值（如 `w-[5.625rem]`），不能寫成內建 class。

---

## 6. 完成定義

- 第 1 節 9 處全部替換完成，第 2 節清單原封未動。
- 第 4 節三項驗證指令皆貼出實際輸出且通過。
- 未改動本清單以外檔案。
- 計畫狀態保持 Draft，由使用者確認後才標記 Done（依全域規則）。
