/**
 * API Keys 管理 Tab
 * 列表展示、建立（彈窗顯示完整 key）、刪除（確認彈窗）
 */
import { useCallback, useEffect, useState } from "react";
import { KeyRound, Loader2, Plus } from "lucide-react";
import { API } from "@/api";
import { useAppStore } from "@/stores/app-store";
import type { ApiKeyInfo } from "@/types";
import { ApiKeyRow } from "./api-keys/ApiKeyRow";
import { CreateApiKeyModal } from "./api-keys/CreateApiKeyModal";
import { DeleteApiKeyModal } from "./api-keys/DeleteApiKeyModal";

// ---------------------------------------------------------------------------
// ApiKeysTab — main export
// ---------------------------------------------------------------------------

export function ApiKeysTab() {
  const [keys, setKeys] = useState<ApiKeyInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<ApiKeyInfo | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await API.listApiKeys();
      setKeys(res);
    } catch (err) {
      useAppStore.getState().pushToast(`載入 API Keys 失敗：${(err as Error).message}`, "error");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const handleCreated = useCallback((newKey: ApiKeyInfo) => {
    setKeys((prev) => [newKey, ...prev]);
  }, []);

  const handleDeleted = useCallback((keyId: number) => {
    setKeys((prev) => prev.filter((k) => k.id !== keyId));
    setDeleteTarget(null);
    useAppStore.getState().pushToast("API Key 已撤銷", "success");
  }, []);

  const handleOpenCreate = useCallback(() => setShowCreate(true), []);
  const handleCloseCreate = useCallback(() => setShowCreate(false), []);
  const handleCloseDelete = useCallback(() => setDeleteTarget(null), []);

  return (
    <>
      {/* 操作欄 */}
      <div className="mb-5 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-gray-100">API Keys</h2>
          <p className="mt-0.5 text-xs text-gray-500">
            用於 OpenClaw 等外部服務透過 Bearer Token 存取 ArcReel API
          </p>
        </div>
        <button
          type="button"
          onClick={handleOpenCreate}
          className="inline-flex items-center gap-1.5 rounded-xl bg-indigo-600 px-3.5 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500 focus-visible:ring-2 focus-visible:ring-indigo-500/60 focus-visible:outline-none"
        >
          <Plus className="h-4 w-4" />
          建立 Key
        </button>
      </div>

      {/* 表格 */}
      <div className="rounded-xl border border-gray-800 bg-gray-900/60 overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center gap-2 py-12 text-gray-500">
            <Loader2 className="h-4 w-4 animate-spin text-indigo-400" />
            <span className="text-sm">載入中…</span>
          </div>
        ) : keys.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-2 py-14 text-gray-600">
            <KeyRound className="h-8 w-8 opacity-40" />
            <p className="text-sm">還沒有 API Key</p>
            <p className="text-xs">點選「建立 Key」建立第一個</p>
          </div>
        ) : (
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-gray-800">
                <th className="py-2.5 pl-4 pr-3 text-xs font-medium text-gray-500">名稱 / 字首</th>
                <th className="hidden px-3 py-2.5 text-xs font-medium text-gray-500 sm:table-cell">
                  建立時間
                </th>
                <th className="hidden px-3 py-2.5 text-xs font-medium text-gray-500 md:table-cell">
                  到期時間
                </th>
                <th className="hidden px-3 py-2.5 text-xs font-medium text-gray-500 lg:table-cell">
                  最近使用
                </th>
                <th className="py-2.5 pl-3 pr-4 text-right text-xs font-medium text-gray-500">
                  操作
                </th>
              </tr>
            </thead>
            <tbody>
              {keys.map((k) => (
                <ApiKeyRow key={k.id} keyInfo={k} onDelete={setDeleteTarget} />
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* 說明 */}
      <p className="mt-3 text-xs text-gray-600">
        在請求標頭中攜帶：
        <code className="mx-1 rounded bg-gray-800 px-1.5 py-0.5 font-mono text-gray-400">
          Authorization: Bearer arc-xxxxxxxx…
        </code>
      </p>

      {/* 彈窗 */}
      {showCreate && (
        <CreateApiKeyModal onClose={handleCloseCreate} onCreated={handleCreated} />
      )}
      {deleteTarget !== null && (
        <DeleteApiKeyModal
          keyInfo={deleteTarget}
          onClose={handleCloseDelete}
          onDeleted={handleDeleted}
        />
      )}
    </>
  );
}
