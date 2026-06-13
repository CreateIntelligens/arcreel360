import { useCallback, useState } from "react";
import { Loader2, Trash2 } from "lucide-react";
import { API } from "@/api";
import { Modal } from "@/components/ui/Modal";
import { useAppStore } from "@/stores/app-store";
import type { ApiKeyInfo } from "@/types";

interface DeleteApiKeyModalProps {
  keyInfo: ApiKeyInfo;
  onClose: () => void;
  onDeleted: (keyId: number) => void;
}

export function DeleteApiKeyModal({ keyInfo, onClose, onDeleted }: DeleteApiKeyModalProps) {
  const [deleting, setDeleting] = useState(false);

  const handleDelete = useCallback(async () => {
    if (deleting) return;
    setDeleting(true);
    try {
      await API.deleteApiKey(keyInfo.id);
      onDeleted(keyInfo.id);
    } catch (err) {
      useAppStore.getState().pushToast(`撤銷失敗：${(err as Error).message}`, "error");
    } finally {
      setDeleting(false);
    }
  }, [deleting, keyInfo.id, onDeleted]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    },
    [onClose],
  );

  return (
    <Modal onKeyDown={handleKeyDown}>
      <div className="w-full max-w-sm rounded-2xl border border-gray-800 bg-gray-900 shadow-2xl shadow-black/50">
        <div className="p-5">
          <div className="flex items-start gap-3">
            <div className="mt-0.5 rounded-full bg-rose-500/10 p-2 text-rose-400">
              <Trash2 className="h-4 w-4" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-gray-100">撤銷 API Key</h2>
              <p className="mt-1.5 text-xs leading-5 text-gray-400">
                將永久撤銷{" "}
                <span className="font-mono text-gray-200">{keyInfo.key_prefix}…</span>（{keyInfo.name}）。
                使用此 Key 的服務將立即失去存取許可權，且操作無法復原。
              </p>
            </div>
          </div>

          <div className="mt-5 flex gap-2">
            <button
              type="button"
              onClick={onClose}
              disabled={deleting}
              className="flex-1 rounded-xl border border-gray-700 bg-gray-900 px-4 py-2.5 text-sm text-gray-300 transition-colors hover:border-gray-600 hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:ring-2 focus-visible:ring-indigo-500/60 focus-visible:outline-none"
            >
              取消
            </button>
            <button
              type="button"
              onClick={() => void handleDelete()}
              disabled={deleting}
              className="flex-1 inline-flex items-center justify-center gap-2 rounded-xl bg-rose-600 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-rose-500 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:ring-2 focus-visible:ring-rose-500/60 focus-visible:outline-none"
            >
              {deleting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Trash2 className="h-4 w-4" />
              )}
              {deleting ? "撤銷中…" : "確認撤銷"}
            </button>
          </div>
        </div>
      </div>
    </Modal>
  );
}
