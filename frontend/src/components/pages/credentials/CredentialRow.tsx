import { memo, useCallback, useState } from "react";
import { Check, Edit2, Loader2, Trash2, Wifi, X } from "lucide-react";
import { API } from "@/api";
import type { ProviderCredential, ProviderTestResult } from "@/types";
import { focusRing, inputCls, inputClsPlaceholder, primaryBtnCls } from "./styles";

interface RowProps {
  cred: ProviderCredential;
  providerId: string;
  isVertex: boolean;
  onChanged: () => void;
}

export const CredentialRow = memo(function CredentialRow({ cred, providerId, isVertex, onChanged }: RowProps) {
  const isAi360 = providerId === "ai360";
  const [editing, setEditing] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<ProviderTestResult | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [saving, setSaving] = useState(false);
  const [draft, setDraft] = useState({
    name: cred.name,
    api_key: "",
    username: cred.username ?? "",
    base_url: cred.base_url ?? "",
  });

  const handleActivate = useCallback(async () => {
    try {
      await API.activateCredential(providerId, cred.id);
      onChanged();
    } catch {
      // 網路錯誤靜默處理，使用者可重試
    }
  }, [providerId, cred.id, onChanged]);

  const handleTest = useCallback(async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const result = await API.testProviderConnection(providerId, cred.id);
      setTestResult(result);
    } catch (e) {
      setTestResult({ success: false, available_models: [], message: String(e) });
    }
    setTesting(false);
  }, [providerId, cred.id]);

  const handleDelete = useCallback(async () => {
    if (!confirmDelete) {
      setConfirmDelete(true);
      return;
    }
    setDeleting(true);
    try {
      await API.deleteCredential(providerId, cred.id);
      onChanged();
    } finally {
      setDeleting(false);
      setConfirmDelete(false);
    }
  }, [providerId, cred.id, confirmDelete, onChanged]);

  const handleSaveEdit = useCallback(async () => {
    const data: Record<string, string> = {};
    if (draft.name && draft.name !== cred.name) data.name = draft.name;
    if (draft.api_key) data.api_key = draft.api_key;
    if (isAi360 && draft.username !== (cred.username ?? "")) data.username = draft.username;
    if (draft.base_url !== (cred.base_url ?? "")) data.base_url = draft.base_url;
    if (Object.keys(data).length === 0) {
      setEditing(false);
      return;
    }
    setSaving(true);
    try {
      await API.updateCredential(providerId, cred.id, data);
      setEditing(false);
      onChanged();
    } finally {
      setSaving(false);
    }
  }, [draft, cred, providerId, isAi360, onChanged]);

  const editPrefix = `cred-edit-${cred.id}`;

  return (
    <div
      className={`rounded-lg border-l-2 px-3 py-2.5 transition-colors ${
        cred.is_active
          ? "border-l-[var(--neon-500)] bg-gray-900/30"
          : "border-l-transparent hover:bg-gray-800/20"
      }`}
    >
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={cred.is_active ? undefined : handleActivate}
          disabled={cred.is_active}
          aria-label={cred.is_active ? "目前使用中" : `啟用 ${cred.name}`}
          className={`h-2.5 w-2.5 flex-shrink-0 rounded-full transition-colors ${focusRing} ${
            cred.is_active
              ? "bg-[var(--neon-500)] shadow-[0_0_6px_var(--neon-500)]"
              : "border border-gray-600 hover:border-gray-400 cursor-pointer"
          }`}
        />

        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-gray-200">{cred.name}</span>
            {cred.is_active && (
              <span className="rounded bg-[var(--neon-500)]/15 px-1.5 py-0.5 text-[10px] font-medium text-[var(--neon-500)]">
                使用中
              </span>
            )}
          </div>
          <div className="mt-0.5 flex items-center gap-2">
            {isAi360 && cred.username && (
              <span className="text-xs text-gray-500">{cred.username}</span>
            )}
            {cred.api_key_masked && (
              <span className="font-mono text-xs text-gray-500">{cred.api_key_masked}</span>
            )}
            {cred.credentials_filename && (
              <span className="text-xs text-gray-500">{cred.credentials_filename}</span>
            )}
          </div>
          {cred.base_url && (
            <div className="mt-0.5 truncate text-xs text-gray-600">{cred.base_url}</div>
          )}
        </div>

        <div className="flex flex-shrink-0 items-center gap-1">
          <button
            type="button"
            onClick={handleTest}
            disabled={testing}
            aria-label={`測試 ${cred.name} 連線`}
            className={`rounded p-1.5 text-gray-500 transition-colors hover:bg-gray-800 hover:text-gray-300 ${focusRing}`}
          >
            {testing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Wifi className="h-3.5 w-3.5" />}
          </button>
          {!isVertex && (
            <button
              type="button"
              onClick={() => {
                setEditing(!editing);
                setDraft({ name: cred.name, api_key: "", username: cred.username ?? "", base_url: cred.base_url ?? "" });
                setTestResult(null);
              }}
              aria-label={`編輯 ${cred.name}`}
              className={`rounded p-1.5 text-gray-500 transition-colors hover:bg-gray-800 hover:text-gray-300 ${focusRing}`}
            >
              <Edit2 className="h-3.5 w-3.5" />
            </button>
          )}
          {!confirmDelete ? (
            <button
              type="button"
              onClick={handleDelete}
              disabled={deleting}
              aria-label={`刪除 ${cred.name}`}
              className={`rounded p-1.5 text-gray-500 transition-colors hover:bg-gray-800 hover:text-rose-400 ${focusRing}`}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          ) : (
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={handleDelete}
                disabled={deleting}
                className={`rounded px-2 py-1 text-xs text-rose-400 transition-colors hover:bg-rose-900/20 ${focusRing}`}
              >
                  {deleting ? <Loader2 className="h-3 w-3 animate-spin" /> : "確認"}
              </button>
              <button
                type="button"
                onClick={() => setConfirmDelete(false)}
                className={`rounded px-2 py-1 text-xs text-gray-500 transition-colors hover:bg-gray-800 hover:text-gray-300 ${focusRing}`}
              >
                取消
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Test result */}
      {testResult && (
        <div
          aria-live="polite"
          className={`mt-2 ml-5.5 rounded-md px-3 py-2 text-xs ${
            testResult.success
              ? "bg-green-900/20 text-green-400"
              : "bg-rose-900/15 text-rose-400"
          }`}
        >
          {testResult.message}
          {testResult.success && testResult.available_models.length > 0 && (
            <div className="mt-1 opacity-70">
              可用模型：{testResult.available_models.join(", ")}
            </div>
          )}
        </div>
      )}

      {/* Inline edit */}
      {editing && (
        <div className="mt-2.5 ml-5.5 space-y-2.5 rounded-lg border border-gray-800 bg-gray-950/60 p-3">
          <div>
            <label htmlFor={`${editPrefix}-name`} className="mb-1 block text-xs text-gray-500">名稱</label>
            <input
              id={`${editPrefix}-name`}
              name="name"
              type="text"
              value={draft.name}
              onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))}
              className={inputCls}
            />
          </div>
          {isAi360 && (
            <div>
              <label htmlFor={`${editPrefix}-username`} className="mb-1 block text-xs text-gray-500">使用者名稱</label>
              <input
                id={`${editPrefix}-username`}
                name="username"
                type="text"
                autoComplete="off"
                value={draft.username}
                onChange={(e) => setDraft((d) => ({ ...d, username: e.target.value }))}
                className={inputCls}
              />
            </div>
          )}
          <div>
            <label htmlFor={`${editPrefix}-apikey`} className="mb-1 block text-xs text-gray-500">
              {isAi360 ? "密碼（留空則保留現有值）" : "API Key（留空則保留現有值）"}
            </label>
            <input
              id={`${editPrefix}-apikey`}
              name={isAi360 ? "password" : "api_key"}
              type="password"
              autoComplete="off"
              value={draft.api_key}
              onChange={(e) => setDraft((d) => ({ ...d, api_key: e.target.value }))}
              placeholder="留空保留現有值…"
              className={inputClsPlaceholder}
            />
          </div>
          {(providerId === "gemini-aistudio" || isAi360) && (
            <div>
              <label htmlFor={`${editPrefix}-baseurl`} className="mb-1 block text-xs text-gray-500">
                {isAi360 ? "Base URL" : "Base URL（可選）"}
              </label>
              <input
                id={`${editPrefix}-baseurl`}
                name="base_url"
                type="url"
                value={draft.base_url}
                onChange={(e) => setDraft((d) => ({ ...d, base_url: e.target.value }))}
                placeholder={isAi360 ? "https://your-domain.com" : "預設使用官方位址…"}
                className={inputClsPlaceholder}
              />
            </div>
          )}
          <div className="flex gap-2 pt-0.5">
            <button
              type="button"
              onClick={() => void handleSaveEdit()}
              disabled={saving}
              className={primaryBtnCls}
            >
              {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />}
              儲存
            </button>
            <button
              type="button"
              onClick={() => setEditing(false)}
              className={`inline-flex items-center gap-1.5 rounded-lg border border-gray-700 px-3 py-1.5 text-xs text-gray-400 transition-colors hover:bg-gray-800 hover:text-gray-200 ${focusRing}`}
            >
              <X className="h-3 w-3" /> 取消
            </button>
          </div>
        </div>
      )}
    </div>
  );
});
