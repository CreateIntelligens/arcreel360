// useConfirm — 命令式的確認對話框 hook
// 用法：
//   const confirm = useConfirm();
//   const ok = await confirm({ message: "確定要刪除？", danger: true });
//   if (!ok) return;
//
// 需要在頂層加上 <ConfirmProvider>（見 src/components/ui/ConfirmProvider.tsx）。

import { createContext, useContext } from "react";

export interface ConfirmOptions {
  title?: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  dismissOnBackdrop?: boolean;
}

export type ConfirmFn = (options: ConfirmOptions) => Promise<boolean>;

export const ConfirmContext = createContext<ConfirmFn | null>(null);

/**
 * 取得命令式的 confirm 函式。
 * 必須在 <ConfirmProvider> 範圍內呼叫，否則丟出錯誤以提早發現遺漏。
 */
export function useConfirm(): ConfirmFn {
  const fn = useContext(ConfirmContext);
  if (!fn) {
    throw new Error(
      "useConfirm 必須在 <ConfirmProvider> 之內使用。請確認頂層佈局已包覆 ConfirmProvider。",
    );
  }
  return fn;
}
