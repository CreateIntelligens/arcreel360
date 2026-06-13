import { AlertTriangle, Loader2 } from "lucide-react";
import { Modal } from "@/components/ui/Modal";
import type { ImportConflictPolicy } from "@/types";

interface ImportConflictDialogProps {
  projectName: string;
  importing: boolean;
  onCancel: () => void;
  onConfirm: (policy: Extract<ImportConflictPolicy, "rename" | "overwrite">) => void;
}

export function ImportConflictDialog({
  projectName,
  importing,
  onCancel,
  onConfirm,
}: ImportConflictDialogProps) {
  return (
    <Modal>
      <div className="w-full max-w-md rounded-2xl border border-amber-400/20 bg-gray-900 p-6 shadow-2xl shadow-black/40">
        <div className="flex items-start gap-3">
          <div className="mt-0.5 rounded-full bg-amber-400/10 p-2 text-amber-300">
            <AlertTriangle className="h-5 w-5" />
          </div>
          <div className="space-y-2">
            <h2 className="text-lg font-semibold text-gray-100">偵測到專案編號重複</h2>
            <p className="text-sm leading-6 text-gray-400">
              匯入包準備使用的專案編號
              <span className="mx-1 rounded bg-gray-800 px-1.5 py-0.5 font-mono text-gray-200">
                {projectName}
              </span>
              已存在。你可以覆蓋現有專案，或自動重新命名後繼續匯入。
            </p>
          </div>
        </div>

        <div className="mt-5 grid gap-3">
          <button
            type="button"
            onClick={() => onConfirm("overwrite")}
            disabled={importing}
            aria-label="覆蓋現有專案"
            className="flex w-full items-center justify-between rounded-xl border border-red-400/25 bg-red-500/10 px-4 py-3 text-left text-sm text-red-100 transition-colors hover:border-red-300/40 hover:bg-red-500/15 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <span>
              <span className="block font-medium">覆蓋現有專案</span>
              <span className="mt-1 block text-xs text-red-200/80">
                使用匯入包內容取代現有專案編號對應的資料
              </span>
            </span>
            {importing && <Loader2 className="h-4 w-4 animate-spin" />}
          </button>

          <button
            type="button"
            onClick={() => onConfirm("rename")}
            disabled={importing}
            aria-label="自動重新命名匯入"
            className="flex w-full items-center justify-between rounded-xl border border-indigo-400/25 bg-indigo-500/10 px-4 py-3 text-left text-sm text-indigo-100 transition-colors hover:border-indigo-300/40 hover:bg-indigo-500/15 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <span>
              <span className="block font-medium">自動重新命名匯入</span>
              <span className="mt-1 block text-xs text-indigo-200/80">
                保留現有專案，新匯入專案自動產生新的內部編號
              </span>
            </span>
            {importing && <Loader2 className="h-4 w-4 animate-spin" />}
          </button>
        </div>

        <div className="mt-5 flex justify-end">
          <button
            type="button"
            onClick={onCancel}
            disabled={importing}
            className="rounded-lg border border-gray-700 px-4 py-2 text-sm text-gray-300 transition-colors hover:border-gray-500 hover:text-white disabled:cursor-not-allowed disabled:opacity-60"
          >
            取消
          </button>
        </div>
      </div>
    </Modal>
  );
}
