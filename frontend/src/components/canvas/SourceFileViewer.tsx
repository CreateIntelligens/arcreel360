import { useState, useEffect, useCallback } from "react";
import { FileText, Edit3, Save, X, Trash2 } from "lucide-react";
import { useLocation } from "wouter";
import { API } from "@/api";
import { useAppStore } from "@/stores/app-store";
import { useConfirm } from "@/hooks/useConfirm";

// ---------------------------------------------------------------------------
// SourceFileViewer — 原始檔預覽/編輯元件
// ---------------------------------------------------------------------------

interface SourceFileViewerProps {
  projectName: string;
  filename: string;
}

export function SourceFileViewer({ projectName, filename }: SourceFileViewerProps) {
  const [, setLocation] = useLocation();
  const confirm = useConfirm();
  const [content, setContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [editContent, setEditContent] = useState("");
  const [saving, setSaving] = useState(false);

  // 載入檔案內容
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setEditing(false);

    API.getSourceContent(projectName, filename)
      .then((text) => {
        if (!cancelled) {
          setContent(text);
          setEditContent(text);
        }
      })
      .catch(() => {
        if (!cancelled) setContent(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [projectName, filename]);

  // 儲存檔案
  const handleSave = useCallback(async () => {
    setSaving(true);
    try {
      await API.saveSourceFile(projectName, filename, editContent);
      setContent(editContent);
      setEditing(false);
    } catch {
      // 可以新增 toast 提示
    } finally {
      setSaving(false);
    }
  }, [projectName, filename, editContent]);

  // 刪除檔案
  const handleDelete = useCallback(async () => {
    const ok = await confirm({
      message: `確定要刪除檔案「${filename}」嗎？此操作無法復原。`,
      danger: true,
    });
    if (!ok) return;
    try {
      await API.deleteSourceFile(projectName, filename);
      useAppStore.getState().invalidateSourceFiles();
      setLocation("/");
    } catch {
      // 可以新增 toast 提示
    }
  }, [projectName, filename, setLocation, confirm]);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center text-gray-500">
        載入檔案中...
      </div>
    );
  }

  if (content === null) {
    return (
      <div className="flex h-full items-center justify-center text-gray-500">
        無法載入檔案 "{filename}"
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      {/* Toolbar */}
      <div className="flex items-center justify-between border-b border-gray-800 px-4 py-2">
        <div className="flex items-center gap-2">
          <FileText className="h-4 w-4 text-gray-400" />
          <h2 className="text-sm font-medium text-gray-200">{filename}</h2>
        </div>
        <div className="flex items-center gap-1">
          {editing ? (
            <>
              <button
                type="button"
                onClick={handleSave}
                disabled={saving}
                className="flex items-center gap-1 rounded px-2 py-1 text-xs text-green-400 transition-colors hover:bg-gray-800 disabled:opacity-50"
              >
                <Save className="h-3.5 w-3.5" />
                {saving ? "儲存中..." : "儲存"}
              </button>
              <button
                type="button"
                onClick={() => { setEditing(false); setEditContent(content); }}
                className="flex items-center gap-1 rounded px-2 py-1 text-xs text-gray-400 transition-colors hover:bg-gray-800"
              >
                <X className="h-3.5 w-3.5" />
                取消
              </button>
            </>
          ) : (
            <>
              <button
                type="button"
                onClick={() => setEditing(true)}
                className="flex items-center gap-1 rounded px-2 py-1 text-xs text-gray-400 transition-colors hover:bg-gray-800 hover:text-gray-200"
              >
                <Edit3 className="h-3.5 w-3.5" />
                編輯
              </button>
              <button
                type="button"
                onClick={handleDelete}
                className="flex items-center gap-1 rounded px-2 py-1 text-xs text-gray-400 transition-colors hover:bg-gray-800 hover:text-red-400"
              >
                <Trash2 className="h-3.5 w-3.5" />
                刪除
              </button>
            </>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto p-4">
        {editing ? (
          <textarea
            value={editContent}
            onChange={(e) => setEditContent(e.target.value)}
            className="h-full w-full resize-none rounded-lg border border-gray-700 bg-gray-800 p-4 font-mono text-sm leading-relaxed text-gray-200 outline-none focus:border-indigo-500"
          />
        ) : (
          <pre className="whitespace-pre-wrap font-mono text-sm leading-relaxed text-gray-300">
            {content}
          </pre>
        )}
      </div>
    </div>
  );
}
