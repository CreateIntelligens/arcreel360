import { useState, useEffect, useCallback } from "react";
import { Edit3, Plus, Save, X } from "lucide-react";
import { API } from "@/api";
import { useAppStore } from "@/stores/app-store";
import { StreamMarkdown } from "@/components/copilot/StreamMarkdown";
import { buildStep1DraftRevisionKey } from "@/utils/project-changes";

interface PreprocessingViewProps {
  projectName: string;
  episode: number;
  contentMode: "narration" | "drama";
}

export function PreprocessingView({
  projectName,
  episode,
  contentMode,
}: PreprocessingViewProps) {
  const pushToast = useAppStore((s) => s.pushToast);
  const draftRevisionKey = buildStep1DraftRevisionKey(episode);
  const draftRevision = useAppStore((s) => s.getEntityRevision(draftRevisionKey));
  const [content, setContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [editContent, setEditContent] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    if (!content) setLoading(true);
    setEditing(false);

    API.getDraftContent(projectName, episode, 1)
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

    return () => {
      cancelled = true;
    };
  }, [projectName, episode, draftRevision]);

  const handleSave = useCallback(async () => {
    setSaving(true);
    try {
      await API.saveDraft(projectName, episode, 1, editContent);
      setContent(editContent);
      setEditing(false);
      pushToast("預處理內容已儲存", "success");
    } catch {
      pushToast("儲存失敗", "error");
    } finally {
      setSaving(false);
    }
  }, [projectName, episode, editContent, pushToast]);

  const startCreate = useCallback(() => {
    setEditContent("");
    setEditing(true);
  }, []);

  const cancelEdit = useCallback(() => {
    setEditing(false);
    setEditContent(content ?? "");
  }, [content]);

  const statusLabel =
    contentMode === "narration" ? "片段拆分已完成" : "規範化劇本已完成";

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center text-gray-500">
        載入預處理內容...
      </div>
    );
  }

  // 尚無草稿且未在編輯：顯示「新增」入口
  if ((content === null || content.trim() === "") && !editing) {
    return (
      <div className="flex h-64 flex-col items-center justify-center gap-3 text-gray-500">
        <span>暫無預處理內容</span>
        <button
          type="button"
          onClick={startCreate}
          className="inline-flex items-center gap-1.5 rounded-lg border border-indigo-500/40 px-3 py-1.5 text-sm text-indigo-300 transition-colors hover:border-indigo-400 hover:bg-indigo-500/10"
        >
          <Plus className="h-4 w-4" />
          新增預處理內容
        </button>
      </div>
    );
  }

  const isCreating = content === null || content.trim() === "";

  return (
    <div className="flex flex-col gap-3">
      {/* Status bar */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {isCreating ? (
            <span className="text-xs text-gray-500">新增預處理內容（格式不限，AI 可讀懂即可）</span>
          ) : (
            <>
              <div className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
              <span className="text-xs text-gray-500">{statusLabel}</span>
            </>
          )}
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
                onClick={cancelEdit}
                className="flex items-center gap-1 rounded px-2 py-1 text-xs text-gray-400 transition-colors hover:bg-gray-800"
              >
                <X className="h-3.5 w-3.5" />
                取消
              </button>
            </>
          ) : (
            <button
              type="button"
              onClick={() => setEditing(true)}
              className="flex items-center gap-1 rounded px-2 py-1 text-xs text-gray-400 transition-colors hover:bg-gray-800 hover:text-gray-200"
            >
              <Edit3 className="h-3.5 w-3.5" />
              編輯
            </button>
          )}
        </div>
      </div>

      {/* Content */}
      {editing ? (
        <textarea
          value={editContent}
          onChange={(e) => setEditContent(e.target.value)}
          autoFocus={isCreating}
          placeholder={isCreating ? "貼上或撰寫這一集的預處理內容…" : undefined}
          className="min-h-[50dvh] w-full resize-y rounded-lg border border-gray-700 bg-gray-800 p-4 font-mono text-sm leading-relaxed text-gray-200 outline-none focus-ring focus-visible:border-indigo-500"
        />
      ) : (
        <div className="prose-invert max-w-none overflow-x-auto rounded-lg border border-gray-800 bg-gray-900/50 p-4 text-sm">
          <StreamMarkdown content={content ?? ""} />
        </div>
      )}
    </div>
  );
}
