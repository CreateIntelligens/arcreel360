// ConfirmDialog — 統一的確認對話框 UI 元件
// 用 Tailwind 配合既有 modal 風格（參考 ArchiveDiagnosticsDialog / OpenClawModal）

import { useEffect } from "react";
import { AlertTriangle, HelpCircle } from "lucide-react";
import { UI_LAYERS } from "@/utils/ui-layers";

export interface ConfirmDialogProps {
  open: boolean;
  title?: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  /** 是否允許點背景關閉，預設 true */
  dismissOnBackdrop?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = "確定",
  cancelLabel = "取消",
  danger = false,
  dismissOnBackdrop = true,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  // ESC 鍵取消
  useEffect(() => {
    if (!open) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onCancel();
      } else if (e.key === "Enter") {
        e.preventDefault();
        onConfirm();
      }
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [open, onCancel, onConfirm]);

  if (!open) return null;

  const headingId = "confirm-dialog-title";
  const bodyId = "confirm-dialog-body";

  const confirmClasses = danger
    ? "border-red-500/40 bg-red-500/90 text-white hover:bg-red-500"
    : "border-sky-500/40 bg-sky-500/90 text-white hover:bg-sky-500";

  const Icon = danger ? AlertTriangle : HelpCircle;
  const iconTone = danger
    ? "bg-red-400/10 text-red-300"
    : "bg-sky-400/10 text-sky-300";

  const handleBackdropClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!dismissOnBackdrop) return;
    if (e.target === e.currentTarget) onCancel();
  };

  return (
    <div
      role="presentation"
      onClick={handleBackdropClick}
      className={`fixed inset-0 ${UI_LAYERS.modal} flex items-center justify-center bg-black/65 px-4`}
    >
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={title ? headingId : undefined}
        aria-describedby={bodyId}
        className="w-full max-w-md rounded-2xl border border-gray-800 bg-gray-900 p-6 shadow-2xl shadow-black/40"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start gap-3">
          <div className={`rounded-full p-2 ${iconTone}`}>
            <Icon className="h-5 w-5" />
          </div>
          <div className="flex-1 space-y-2">
            {title && (
              <h2 id={headingId} className="text-lg font-semibold text-gray-100">
                {title}
              </h2>
            )}
            <p
              id={bodyId}
              className="whitespace-pre-line text-sm leading-6 text-gray-300"
            >
              {message}
            </p>
          </div>
        </div>

        <div className="mt-6 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-lg border border-gray-700 px-4 py-1.5 text-sm text-gray-300 transition-colors hover:border-gray-500 hover:text-white"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            autoFocus
            className={`rounded-lg border px-4 py-1.5 text-sm font-medium transition-colors ${confirmClasses}`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
