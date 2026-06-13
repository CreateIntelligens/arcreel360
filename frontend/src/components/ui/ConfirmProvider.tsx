// ConfirmProvider — 提供命令式 confirm() 的 Context Provider
// 在頂層渲染一個 <ConfirmDialog>，由 useConfirm() 透過 Promise 觸發。

import { useCallback, useMemo, useRef, useState } from "react";
import { ConfirmContext, type ConfirmOptions } from "@/hooks/useConfirm";
import { ConfirmDialog } from "./ConfirmDialog";

interface InternalState {
  open: boolean;
  options: ConfirmOptions | null;
}

export function ConfirmProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<InternalState>({ open: false, options: null });
  // 用 ref 保存當前 Promise 的 resolver，避免被 stale closure 抓住
  const resolverRef = useRef<((value: boolean) => void) | null>(null);

  const confirm = useCallback((options: ConfirmOptions): Promise<boolean> => {
    // 若上一個還沒結束（理論上不該發生），先以 false 解決舊的
    if (resolverRef.current) {
      resolverRef.current(false);
      resolverRef.current = null;
    }
    return new Promise<boolean>((resolve) => {
      resolverRef.current = resolve;
      setState({ open: true, options });
    });
  }, []);

  const close = useCallback((result: boolean) => {
    const resolver = resolverRef.current;
    resolverRef.current = null;
    setState({ open: false, options: null });
    if (resolver) resolver(result);
  }, []);

  const handleConfirm = useCallback(() => close(true), [close]);
  const handleCancel = useCallback(() => close(false), [close]);

  // confirm 函式本身穩定（useCallback 空依賴），可放心 memo
  const value = useMemo(() => confirm, [confirm]);

  return (
    <ConfirmContext.Provider value={value}>
      {children}
      <ConfirmDialog
        open={state.open}
        title={state.options?.title}
        message={state.options?.message ?? ""}
        confirmLabel={state.options?.confirmLabel}
        cancelLabel={state.options?.cancelLabel}
        danger={state.options?.danger}
        dismissOnBackdrop={state.options?.dismissOnBackdrop}
        onConfirm={handleConfirm}
        onCancel={handleCancel}
      />
    </ConfirmContext.Provider>
  );
}
