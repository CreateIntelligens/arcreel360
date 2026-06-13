import { useEffect, useState } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";
import { Modal } from "@/components/ui/Modal";

interface DeleteProjectDialogProps {
  projectName: string;
  projectTitle: string;
  deleting: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

const CONFIRM_WORD = "DELETE";

export function DeleteProjectDialog({
  projectName,
  projectTitle,
  deleting,
  onCancel,
  onConfirm,
}: DeleteProjectDialogProps) {
  const [input, setInput] = useState("");
  const canDelete = input === CONFIRM_WORD && !deleting;
  const displayName = projectTitle || projectName;

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !deleting) {
        onCancel();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [deleting, onCancel]);

  return (
    <Modal onBackdropClick={deleting ? undefined : onCancel}>
      <div className="workbench-panel-strong relative w-full max-w-md rounded-[1.4rem] p-6 shadow-2xl shadow-black/40">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-rose-500/15">
            <AlertTriangle className="h-5 w-5 text-rose-400" />
          </div>
          <h2 className="text-lg font-semibold text-[color:var(--wb-text-primary)]">
            刪除專案
          </h2>
        </div>

        <p className="mt-4 text-sm leading-6 text-[color:var(--wb-text-muted)]">
          即將永久刪除專案「
          <span className="font-medium text-[color:var(--wb-text-primary)]">
            {displayName}
          </span>
          」。此操作會移除整個專案目錄，<span className="text-rose-400">無法復原</span>。
        </p>

        <label className="mt-4 block text-sm text-[color:var(--wb-text-muted)]">
          請輸入 <span className="font-mono font-semibold text-rose-400">{CONFIRM_WORD}</span> 以確認：
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={deleting}
            autoFocus
            className="mt-2 w-full rounded-xl border border-white/10 bg-black/30 px-3 py-2 font-mono text-sm text-[color:var(--wb-text-primary)] outline-none focus:border-rose-400/60 disabled:opacity-60"
            placeholder={CONFIRM_WORD}
          />
        </label>

        <div className="mt-6 flex justify-end gap-3">
          <button
            type="button"
            onClick={onCancel}
            disabled={deleting}
            className="workbench-button-secondary rounded-xl px-4 py-2 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-60"
          >
            取消
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={!canDelete}
            className="inline-flex items-center gap-1.5 rounded-xl bg-rose-600 px-4 py-2 text-sm font-medium text-white hover:bg-rose-500 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {deleting && <Loader2 className="h-4 w-4 animate-spin" />}
            {deleting ? "刪除中..." : "確認刪除"}
          </button>
        </div>
      </div>
    </Modal>
  );
}
