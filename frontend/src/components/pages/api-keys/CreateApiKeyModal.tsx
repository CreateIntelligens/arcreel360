import { useCallback, useMemo, useState } from "react";
import {
  AlertTriangle,
  Check,
  Copy,
  KeyRound,
  Loader2,
  Plus,
  X,
} from "lucide-react";
import { API } from "@/api";
import { Modal } from "@/components/ui/Modal";
import { useAppStore } from "@/stores/app-store";
import { copyText } from "@/utils/clipboard";
import type { ApiKeyInfo, CreateApiKeyResponse } from "@/types";

interface CreateApiKeyModalProps {
  onClose: () => void;
  onCreated: (key: ApiKeyInfo) => void;
}

export function CreateApiKeyModal({ onClose, onCreated }: CreateApiKeyModalProps) {
  const [name, setName] = useState("");
  const [expiresDays, setExpiresDays] = useState<number | "">(30);
  const [creating, setCreating] = useState(false);
  const [created, setCreated] = useState<CreateApiKeyResponse | null>(null);
  const [copied, setCopied] = useState(false);

  const canCreate = useMemo(() => name.trim().length > 0, [name]);

  const handleCreate = useCallback(async () => {
    if (!canCreate || creating) return;
    setCreating(true);
    try {
      // expiresDays === "" 或 0 時傳送 0（後端解釋為永不過期）；
      // 正整數直接傳遞；undefined 讓後端使用預設值（30天）。
      const days: number | undefined = expiresDays === "" ? 0 : expiresDays;
      const res = await API.createApiKey(name.trim(), days);
      setCreated(res);
      onCreated({
        id: res.id,
        name: res.name,
        key_prefix: res.key_prefix,
        created_at: res.created_at,
        expires_at: res.expires_at,
        last_used_at: null,
      });
    } catch (err) {
      useAppStore.getState().pushToast(`建立失敗: ${(err as Error).message}`, "error");
    } finally {
      setCreating(false);
    }
  }, [canCreate, creating, expiresDays, name, onCreated]);

  const handleCopy = useCallback(async () => {
    if (!created?.key) return;
    await copyText(created.key);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [created?.key]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.nativeEvent.isComposing) return;
      if (e.key === "Enter" && !created && canCreate) void handleCreate();
      if (e.key === "Escape") onClose();
    },
    [canCreate, created, handleCreate, onClose],
  );

  return (
    <Modal onKeyDown={handleKeyDown}>
      <div className="w-full max-w-md rounded-2xl border border-gray-800 bg-gray-900 shadow-2xl shadow-black/50">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-gray-800 px-5 py-4">
          <div className="flex items-center gap-2.5">
            <div className="rounded-lg border border-indigo-500/30 bg-indigo-500/10 p-1.5 text-indigo-400">
              <KeyRound className="h-4 w-4" />
            </div>
            <h2 className="text-sm font-semibold text-gray-100">
              {created ? "API Key 已建立" : "建立 API Key"}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-gray-500 transition-colors hover:bg-gray-800 hover:text-gray-300 focus-visible:ring-2 focus-visible:ring-indigo-500/60 focus-visible:outline-none"
            aria-label="關閉"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="p-5">
          {created ? (
            /* ——— 建立成功檢視 ——— */
            <div className="space-y-4">
              {/* 僅此一次警告 */}
              <div className="flex items-start gap-2.5 rounded-xl border border-amber-500/20 bg-amber-500/8 px-3 py-3">
                <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-400" />
                <p className="text-xs leading-5 text-amber-200">
                  請立即複製並妥善儲存此 API Key。基於安全考量，完整金鑰<strong className="font-semibold"> 只會在建立時顯示一次</strong>，關閉後將無法再次檢視。
                </p>
              </div>

              {/* 金鑰展示 */}
              <div>
                <div className="mb-1.5 text-xs font-medium text-gray-400">你的 API Key</div>
                <div className="group relative flex items-center gap-2 rounded-xl border border-gray-700 bg-gray-950 px-3 py-2.5">
                  <code className="flex-1 overflow-x-auto whitespace-nowrap font-mono text-xs text-indigo-300 scrollbar-none">
                    {created.key}
                  </code>
                  <button
                    type="button"
                    onClick={() => void handleCopy()}
                    className="flex-shrink-0 rounded-md p-1 text-gray-500 transition-colors hover:bg-gray-800 hover:text-gray-200 focus-visible:ring-2 focus-visible:ring-indigo-500/60 focus-visible:outline-none"
                    aria-label="複製金鑰"
                  >
                    {copied ? (
                      <Check className="h-3.5 w-3.5 text-emerald-400" />
                    ) : (
                      <Copy className="h-3.5 w-3.5" />
                    )}
                  </button>
                </div>
              </div>

              {/* 元資訊 */}
              <div className="grid grid-cols-2 gap-3 text-xs">
                <div className="rounded-lg border border-gray-800 bg-gray-950/50 px-3 py-2">
                  <div className="text-gray-500">名稱</div>
                  <div className="mt-0.5 truncate font-medium text-gray-200">{created.name}</div>
                </div>
                <div className="rounded-lg border border-gray-800 bg-gray-950/50 px-3 py-2">
                  <div className="text-gray-500">字首</div>
                  <div className="mt-0.5 font-mono font-medium text-gray-200">{created.key_prefix}…</div>
                </div>
              </div>

              <button
                type="button"
                onClick={onClose}
                className="w-full rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-indigo-500 focus-visible:ring-2 focus-visible:ring-indigo-500/60 focus-visible:outline-none"
              >
                已複製，關閉
              </button>
            </div>
          ) : (
            /* ——— 建立表單檢視 ——— */
            <div className="space-y-4">
              <div>
                <label className="mb-1.5 block text-xs font-medium text-gray-300">
                  名稱 <span className="text-rose-400">*</span>
                </label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="例如：OpenClaw 整合"
                  autoFocus
                  className="w-full rounded-xl border border-gray-700 bg-gray-950 px-3 py-2.5 text-sm text-gray-200 placeholder:text-gray-600 focus:border-indigo-500/60 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500/40"
                />
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-medium text-gray-300">
                  有效期（天）
                </label>
                <input
                  type="number"
                  min={1}
                  max={3650}
                  value={expiresDays}
                  onChange={(e) =>
                    setExpiresDays(e.target.value === "" ? "" : Number(e.target.value))
                  }
                  placeholder="留空則不過期"
                  className="w-full rounded-xl border border-gray-700 bg-gray-950 px-3 py-2.5 text-sm text-gray-200 placeholder:text-gray-600 focus:border-indigo-500/60 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500/40"
                />
                <p className="mt-1 text-xs text-gray-600">預設 30 天；留空則永不過期</p>
              </div>

              <div className="flex gap-2 pt-1">
                <button
                  type="button"
                  onClick={onClose}
                  className="flex-1 rounded-xl border border-gray-700 bg-gray-900 px-4 py-2.5 text-sm text-gray-300 transition-colors hover:border-gray-600 hover:bg-gray-800 focus-visible:ring-2 focus-visible:ring-indigo-500/60 focus-visible:outline-none"
                >
                  取消
                </button>
                <button
                  type="button"
                  onClick={() => void handleCreate()}
                  disabled={!canCreate || creating}
                  className="flex-1 inline-flex items-center justify-center gap-2 rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:ring-2 focus-visible:ring-indigo-500/60 focus-visible:outline-none"
                >
                  {creating ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Plus className="h-4 w-4" />
                  )}
                  {creating ? "建立中…" : "建立"}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </Modal>
  );
}
