import { useEffect } from "react";

/**
 * 當有未儲存更改時，阻止使用者關閉/重新整理標籤頁。
 */
export function useWarnUnsaved(isDirty: boolean) {
  useEffect(() => {
    if (!isDirty) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [isDirty]);
}
