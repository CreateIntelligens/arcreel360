import { useCallback, useMemo } from "react";
import { Trash2 } from "lucide-react";
import type { ApiKeyInfo } from "@/types";
import { formatDate, isExpired } from "./utils";

interface ApiKeyRowProps {
  keyInfo: ApiKeyInfo;
  onDelete: (keyInfo: ApiKeyInfo) => void;
}

export function ApiKeyRow({ keyInfo, onDelete }: ApiKeyRowProps) {
  const expired = useMemo(() => isExpired(keyInfo.expires_at), [keyInfo.expires_at]);

  const handleDelete = useCallback(() => onDelete(keyInfo), [keyInfo, onDelete]);

  return (
    <tr className="group border-t border-gray-800/70 transition-colors hover:bg-gray-800/30">
      {/* 名稱 */}
      <td className="py-3 pl-4 pr-3">
        <div className="flex items-center gap-2">
          <div className="min-w-0">
            <div className="truncate text-sm font-medium text-gray-100">{keyInfo.name}</div>
            <div className="mt-0.5 font-mono text-xs text-gray-500">{keyInfo.key_prefix}…</div>
          </div>
        </div>
      </td>

      {/* 建立時間 */}
      <td className="hidden px-3 py-3 sm:table-cell">
        <span className="text-xs text-gray-400">{formatDate(keyInfo.created_at)}</span>
      </td>

      {/* 過期時間 */}
      <td className="hidden px-3 py-3 md:table-cell">
        {keyInfo.expires_at ? (
          <span
            className={`text-xs ${expired ? "font-medium text-rose-400" : "text-gray-400"}`}
          >
            {expired ? "已過期 · " : ""}
            {formatDate(keyInfo.expires_at)}
          </span>
        ) : (
          <span className="text-xs text-gray-600">永不過期</span>
        )}
      </td>

      {/* 最近使用 */}
      <td className="hidden px-3 py-3 lg:table-cell">
        <span className="text-xs text-gray-400">{formatDate(keyInfo.last_used_at)}</span>
      </td>

      {/* 操作 */}
      <td className="py-3 pl-3 pr-4 text-right">
        <button
          type="button"
          onClick={handleDelete}
          className="inline-flex items-center gap-1 rounded-lg border border-transparent px-2 py-1 text-xs text-gray-500 transition-colors hover:border-rose-500/30 hover:bg-rose-500/8 hover:text-rose-400 focus-visible:ring-2 focus-visible:ring-indigo-500/60 focus-visible:outline-none"
          aria-label={`撤銷 ${keyInfo.name}`}
        >
          <Trash2 className="h-3.5 w-3.5" />
          撤銷
        </button>
      </td>
    </tr>
  );
}
