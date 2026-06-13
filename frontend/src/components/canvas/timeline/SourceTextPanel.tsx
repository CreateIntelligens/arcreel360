import { useEffect, useState } from "react";
import { BookOpen, ChevronRight, ChevronLeft, Copy, Check, Edit3, Save, X } from "lucide-react";
import { API } from "@/api";
import { useAppStore } from "@/stores/app-store";

interface Paragraph {
  id: string;
  content: string;
}

interface SourceTextPanelProps {
  projectName: string;
  episode: number;
  contentMode: "narration" | "drama";
  activeSegmentIndex: number | null;
  onSelectSegmentIndex?: (index: number) => void;
}

export function SourceTextPanel({
  projectName,
  episode,
  contentMode,
  activeSegmentIndex,
  onSelectSegmentIndex,
}: SourceTextPanelProps) {
  const [open, setOpen] = useState(false);
  const [paragraphs, setParagraphs] = useState<Paragraph[]>([]);
  const [loading, setLoading] = useState(false);
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [editValue, setEditValue] = useState("");
  const [savingIndex, setSavingIndex] = useState<number | null>(null);

  const segmentLabel = contentMode === "drama" ? "場景" : "段落";

  useEffect(() => {
    if (!projectName || !episode) return;
    let cancelled = false;
    setLoading(true);
    setEditingIndex(null);
    API.getSourceParagraphs(projectName, episode)
      .then((res) => {
        if (!cancelled) {
          setParagraphs(res.paragraphs || []);
        }
      })
      .catch((err) => {
        console.error("Failed to load source paragraphs:", err);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [projectName, episode]);

  const handleCopy = (text: string, index: number) => {
    navigator.clipboard.writeText(text);
    setCopiedIndex(index);
    useAppStore.getState().pushToast("已複製原文段落", "success");
    setTimeout(() => setCopiedIndex(null), 2000);
  };

  const startEdit = (index: number, content: string) => {
    setEditingIndex(index);
    setEditValue(content);
  };

  const cancelEdit = () => {
    setEditingIndex(null);
    setEditValue("");
  };

  const handleSave = async (index: number) => {
    const para = paragraphs[index];
    if (!para) return;
    const next = editValue.trim();
    if (!next || next === para.content) {
      cancelEdit();
      return;
    }
    setSavingIndex(index);
    try {
      const res = await API.updateSourceParagraph(projectName, episode, para.id, next);
      setParagraphs((prev) =>
        prev.map((p, i) => (i === index ? { ...p, content: res.content } : p)),
      );
      setEditingIndex(null);
      setEditValue("");
      useAppStore.getState().pushToast("已更新原文段落並同步預處理", "success");
    } catch (err) {
      console.error("Failed to update source paragraph:", err);
      useAppStore.getState().pushToast("更新原文段落失敗", "error");
    } finally {
      setSavingIndex(null);
    }
  };

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="fixed right-4 top-1/2 z-20 -translate-y-1/2 rounded-l-xl border border-gray-700 bg-gray-900 p-2.5 text-gray-400 hover:bg-gray-800 hover:text-gray-200 shadow-xl transition-all flex flex-col items-center gap-1"
        title="展開原文對照"
      >
        <ChevronLeft className="h-4 w-4" />
        <BookOpen className="h-4 w-4" />
      </button>
    );
  }

  return (
    <div className="flex h-full w-1/3 min-w-[20rem] max-w-[28rem] shrink-0 flex-col border-l border-gray-800 bg-gray-950/50">
      <div className="flex items-center justify-between border-b border-gray-800 p-3.5">
        <div className="flex items-center gap-2">
          <BookOpen className="h-4 w-4 text-indigo-400" />
          <h4 className="text-sm font-semibold text-gray-200">原文對照</h4>
        </div>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="rounded-lg p-1 text-gray-500 hover:bg-gray-800 hover:text-gray-300"
          title="收合"
        >
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {loading ? (
          <div className="py-8 text-center text-xs text-gray-600">載入原文段落中...</div>
        ) : paragraphs.length === 0 ? (
          <div className="py-8 text-center text-xs text-gray-600">
            未找到 Step 1 預處理段落，請先執行預處理。
          </div>
        ) : (
          paragraphs.map((para, idx) => {
            const isActive = activeSegmentIndex === idx;
            const isEditing = editingIndex === idx;
            return (
              <div
                key={para.id || idx}
                onClick={() => !isEditing && onSelectSegmentIndex?.(idx)}
                className={`group relative rounded-xl border p-3 transition-all ${
                  isEditing ? "cursor-default" : "cursor-pointer"
                } ${
                  isActive
                    ? "border-indigo-500/50 bg-indigo-500/10 text-gray-100 ring-1 ring-indigo-500/30"
                    : "border-gray-800 bg-gray-900/40 text-gray-400 hover:border-gray-700 hover:text-gray-300"
                }`}
              >
                <div className="mb-1 flex items-center justify-between text-[10px] font-medium tracking-wider uppercase text-gray-500">
                  <span>
                    {segmentLabel} {idx + 1}
                  </span>
                  <div className="flex items-center gap-0.5">
                    {isEditing ? (
                      <>
                        <button
                          type="button"
                          disabled={savingIndex === idx}
                          onClick={(e) => {
                            e.stopPropagation();
                            handleSave(idx);
                          }}
                          className="p-0.5 rounded text-emerald-400 hover:bg-gray-800 disabled:opacity-50 transition-colors"
                          title="儲存"
                        >
                          <Save className="h-3 w-3" />
                        </button>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            cancelEdit();
                          }}
                          className="p-0.5 rounded text-gray-500 hover:bg-gray-800 hover:text-gray-300 transition-colors"
                          title="取消"
                        >
                          <X className="h-3 w-3" />
                        </button>
                      </>
                    ) : (
                      <>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            startEdit(idx, para.content);
                          }}
                          className="opacity-0 group-hover:opacity-100 p-0.5 rounded text-gray-500 hover:bg-gray-800 hover:text-gray-300 transition-opacity"
                          title="編輯段落"
                        >
                          <Edit3 className="h-3 w-3" />
                        </button>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleCopy(para.content, idx);
                          }}
                          className="opacity-0 group-hover:opacity-100 p-0.5 rounded text-gray-500 hover:bg-gray-800 hover:text-gray-300 transition-opacity"
                          title="複製內容"
                        >
                          {copiedIndex === idx ? (
                            <Check className="h-3 w-3 text-emerald-400" />
                          ) : (
                            <Copy className="h-3 w-3" />
                          )}
                        </button>
                      </>
                    )}
                  </div>
                </div>
                {isEditing ? (
                  <textarea
                    autoFocus
                    value={editValue}
                    onClick={(e) => e.stopPropagation()}
                    onChange={(e) => setEditValue(e.target.value)}
                    className="w-full resize-y rounded-lg border border-indigo-500/40 bg-gray-900 p-2 text-xs leading-relaxed text-gray-100 outline-none focus:border-indigo-500"
                    rows={Math.max(3, Math.ceil(editValue.length / 24))}
                  />
                ) : (
                  <p className="text-xs leading-relaxed whitespace-pre-wrap select-text">{para.content}</p>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
