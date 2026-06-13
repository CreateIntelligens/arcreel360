import { useState, useEffect, useCallback, useRef } from "react";
import { Loader2, Plus } from "lucide-react";
import { API } from "@/api";
import type { ProviderCredential } from "@/types";
import { CredentialRow } from "./credentials/CredentialRow";
import { AddCredentialForm } from "./credentials/AddCredentialForm";
import { focusRing } from "./credentials/styles";

//CredentialList — main export


interface Props {
  providerId: string;
  onChanged?: () => void;
}

export function CredentialList({ providerId, onChanged }: Props) {
  const [credentials, setCredentials] = useState<ProviderCredential[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const isVertex = providerId === "gemini-vertex";

  // 用 ref 儲存 onChanged 以穩定 refresh 引用，避免父元件 re-render 導致無限迴圈
  const onChangedRef = useRef(onChanged);
  onChangedRef.current = onChanged;

  const refresh = useCallback(async () => {
    try {
      const { credentials: creds } = await API.listCredentials(providerId);
      setCredentials(creds);
    } finally {
      setLoading(false);
    }
  }, [providerId]);

  // 使用者操作後：重新整理列表 + 通知父元件
  const handleChanged = useCallback(async () => {
    await refresh();
    onChangedRef.current?.();
  }, [refresh]);

  useEffect(() => {
    setLoading(true);
    setShowAdd(false);
    void refresh();
  }, [refresh]);

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-4 text-sm text-gray-500">
        <Loader2 className="h-4 w-4 animate-spin" /> 載入中…
      </div>
    );
  }

  return (
    <div>
      <div className="mb-2.5 flex items-center justify-between">
        <h4 className="text-sm font-medium text-gray-300">金鑰管理</h4>
        {!showAdd && (
          <button
            type="button"
            onClick={() => setShowAdd(true)}
            className={`inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-[var(--neon-500)] transition-colors hover:bg-[var(--neon-500)]/10 ${focusRing}`}
          >
            <Plus className="h-3 w-3" /> 新增金鑰
          </button>
        )}
      </div>

      {credentials.length === 0 && !showAdd && (
        <div className="rounded-lg border border-dashed border-gray-700 px-4 py-6 text-center">
          <p className="text-sm text-gray-500">暫無金鑰</p>
          <button
            type="button"
            onClick={() => setShowAdd(true)}
            className={`mt-2 inline-flex items-center gap-1 text-xs text-[var(--neon-500)] transition-colors hover:text-[var(--neon-400)] ${focusRing}`}
          >
            <Plus className="h-3 w-3" /> 新增第一個金鑰
          </button>
        </div>
      )}

      <div className="space-y-1">
        {credentials.map((c) => (
          <CredentialRow
            key={c.id}
            cred={c}
            providerId={providerId}
            isVertex={isVertex}
            onChanged={handleChanged}
          />
        ))}
      </div>

      {showAdd && (
        <div className="mt-2">
          <AddCredentialForm
            providerId={providerId}
            isVertex={isVertex}
            onCreated={() => {
              setShowAdd(false);
              void handleChanged();
            }}
            onCancel={() => setShowAdd(false)}
          />
        </div>
      )}
    </div>
  );
}
