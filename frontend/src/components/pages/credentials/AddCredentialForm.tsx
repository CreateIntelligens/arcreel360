import { useRef, useState } from "react";
import { Loader2, Plus, Upload } from "lucide-react";
import { API } from "@/api";
import { focusRing, inputCls, inputClsPlaceholder, primaryBtnCls } from "./styles";

interface AddFormProps {
  providerId: string;
  isVertex: boolean;
  onCreated: () => void;
  onCancel: () => void;
}

export function AddCredentialForm({ providerId, isVertex, onCreated, onCancel }: AddFormProps) {
  const isAi360 = providerId === "ai360";
  const [name, setName] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [username, setUsername] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleSubmit = async () => {
    if (!name.trim()) return;
    setSaving(true);
    setError(null);
    try {
      if (isVertex) {
        const file = fileRef.current?.files?.[0];
        if (!file) {
          setError("請選擇憑證檔案");
          setSaving(false);
          return;
        }
        await API.uploadVertexCredential(name, file);
      } else if (isAi360) {
        if (!username.trim() || !apiKey.trim() || !baseUrl.trim()) {
          setError("請輸入使用者名稱、密碼與 Base URL");
          setSaving(false);
          return;
        }
        await API.createCredential(providerId, {
          name: name.trim(),
          username: username.trim(),
          api_key: apiKey, // ai360 的密碼存於 api_key 欄
          base_url: baseUrl.trim(),
        });
      } else {
        if (!apiKey.trim()) {
          setError("請輸入 API Key");
          setSaving(false);
          return;
        }
        await API.createCredential(providerId, {
          name: name.trim(),
          api_key: apiKey || undefined,
          base_url: baseUrl || undefined,
        });
      }
      onCreated();
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rounded-lg border border-gray-700 bg-gray-950/60 p-3 space-y-2.5">
      <div>
        <label htmlFor="cred-add-name" className="mb-1 block text-xs text-gray-500">名稱 <span className="text-rose-400">*</span></label>
        <input
          id="cred-add-name"
          name="name"
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="例如：個人帳號…"
          className={inputClsPlaceholder}
          autoFocus
        />
      </div>
      {isVertex ? (
        <div>
          <label htmlFor="cred-add-file" className="mb-1 block text-xs text-gray-500">憑證檔案 <span className="text-rose-400">*</span></label>
          <button
            id="cred-add-file"
            type="button"
            onClick={() => fileRef.current?.click()}
            className={`inline-flex items-center gap-1.5 rounded-lg border border-gray-700 px-3 py-1.5 text-xs text-gray-300 transition-colors hover:bg-gray-800 ${focusRing}`}
          >
            <Upload className="h-3 w-3" />
            {fileRef.current?.files?.[0]?.name ?? "選擇 JSON 檔案…"}
          </button>
          <input ref={fileRef} type="file" accept=".json,application/json" className="hidden" onChange={() => setError(null)} />
        </div>
      ) : isAi360 ? (
        <>
          <div>
            <label htmlFor="cred-add-username" className="mb-1 block text-xs text-gray-500">使用者名稱 <span className="text-rose-400">*</span></label>
            <input
              id="cred-add-username"
              name="username"
              type="text"
              autoComplete="off"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className={inputCls}
            />
          </div>
          <div>
            <label htmlFor="cred-add-password" className="mb-1 block text-xs text-gray-500">密碼 <span className="text-rose-400">*</span></label>
            <input
              id="cred-add-password"
              name="password"
              type="password"
              autoComplete="off"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              className={inputCls}
            />
          </div>
          <div>
            <label htmlFor="cred-add-ai360-baseurl" className="mb-1 block text-xs text-gray-500">Base URL <span className="text-rose-400">*</span></label>
            <input
              id="cred-add-ai360-baseurl"
              name="base_url"
              type="url"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="https://your-domain.com"
              className={inputClsPlaceholder}
            />
          </div>
        </>
      ) : (
        <>
          <div>
            <label htmlFor="cred-add-apikey" className="mb-1 block text-xs text-gray-500">API Key <span className="text-rose-400">*</span></label>
            <input
              id="cred-add-apikey"
              name="api_key"
              type="password"
              autoComplete="off"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              className={inputCls}
            />
          </div>
          {providerId === "gemini-aistudio" && (
            <div>
              <label htmlFor="cred-add-baseurl" className="mb-1 block text-xs text-gray-500">Base URL（可選）</label>
              <input
                id="cred-add-baseurl"
                name="base_url"
                type="url"
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder="預設使用官方位址…"
                className={inputClsPlaceholder}
              />
            </div>
          )}
        </>
      )}
      {error && <p className="text-xs text-rose-400" aria-live="polite">{error}</p>}
      <div className="flex gap-2 pt-0.5">
        <button
          type="button"
          onClick={() => void handleSubmit()}
          disabled={saving || !name.trim()}
          className={primaryBtnCls}
        >
          {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Plus className="h-3 w-3" />}
          新增
        </button>
        <button
          type="button"
          onClick={onCancel}
          className={`rounded-lg border border-gray-700 px-3 py-1.5 text-xs text-gray-400 transition-colors hover:bg-gray-800 hover:text-gray-200 ${focusRing}`}
        >
          取消
        </button>
      </div>
    </div>
  );
}
