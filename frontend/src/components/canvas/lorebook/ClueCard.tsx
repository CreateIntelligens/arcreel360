import { useEffect, useState } from "react";
import { Pencil, Puzzle, Trash2 } from "lucide-react";
import { API } from "@/api";
import { VersionTimeMachine } from "@/components/canvas/timeline/VersionTimeMachine";
import { AspectFrame } from "@/components/ui/AspectFrame";
import { PreviewableImageFrame } from "@/components/ui/PreviewableImageFrame";
import { useProjectsStore } from "@/stores/projects-store";
import { useAppStore } from "@/stores/app-store";
import { useConfirm } from "@/hooks/useConfirm";
import type { Clue } from "@/types";
import { LorebookDescriptionField } from "./LorebookDescriptionField";
import { LorebookImageGenerateControls } from "./LorebookImageGenerateControls";
import { LorebookReferenceImageField } from "./LorebookReferenceImageField";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface ClueSavePayload {
  description: string;
  imageBackend?: string | null;
}

interface ClueCardProps {
  name: string;
  clue: Clue;
  projectName: string;
  onSave: (name: string, payload: ClueSavePayload) => Promise<void>;
  onGenerate: (name: string) => void;
  /** 上傳參考圖（multipart）。提供時才顯示參考圖上傳入口。 */
  onUploadReference?: (name: string, file: File) => Promise<void> | void;
  onRemoveReference?: (name: string) => Promise<void> | void;
  onDelete?: (name: string) => Promise<void> | void;
  onRename?: (oldName: string, newName: string) => Promise<void> | void;
  onRestoreVersion?: () => Promise<void> | void;
  generating?: boolean;
  modelOptions?: {
    image: string[];
    text?: string[];
    providerNames: Record<string, string>;
  };
}

// ---------------------------------------------------------------------------
// ClueCard
// ---------------------------------------------------------------------------

export function ClueCard({
  name,
  clue,
  projectName,
  onSave,
  onGenerate,
  onUploadReference,
  onRemoveReference,
  onDelete,
  onRename,
  onRestoreVersion,
  generating = false,
  modelOptions,
}: ClueCardProps) {
  const confirm = useConfirm();
  const [textModel, setTextModel] = useState<string | null>(null);
  const [renaming, setRenaming] = useState(false);
  const [nameDraft, setNameDraft] = useState(name);

  useEffect(() => {
    setNameDraft(name);
  }, [name]);

  const commitRename = async () => {
    const trimmed = nameDraft.trim();
    setRenaming(false);
    if (!trimmed || trimmed === name || !onRename) {
      setNameDraft(name);
      return;
    }
    await onRename(name, trimmed);
  };
  const sheetFp = useProjectsStore(
    (s) => clue.clue_sheet ? s.getAssetFingerprint(clue.clue_sheet) : null,
  );
  const referenceFp = useProjectsStore(
    (s) => clue.reference_image ? s.getAssetFingerprint(clue.reference_image) : null,
  );
  const [description, setDescription] = useState(clue.description);
  const [imageBackend, setImageBackend] = useState(clue.image_backend ?? "");
  const [imgError, setImgError] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [aiGenerating, setAiGenerating] = useState(false);

  const isDirty =
    description !== clue.description ||
    imageBackend !== (clue.image_backend ?? "");

  useEffect(() => {
    setDescription(clue.description);
    setImageBackend(clue.image_backend ?? "");
  }, [clue.description, clue.image_backend]);

  useEffect(() => {
    setImgError(false);
  }, [clue.clue_sheet, sheetFp]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await onSave(name, {
        description,
        imageBackend: imageBackend || null,
      });
    } finally {
      setSaving(false);
    }
  };

  const handleModelChange = async (value: string) => {
    setImageBackend(value);
    setSaving(true);
    try {
      await onSave(name, {
        description,
        imageBackend: value || null,
      });
      useAppStore.getState().pushToast("模型設定已更新", "success");
    } catch (err) {
      useAppStore.getState().pushToast(`模型設定更新失敗: ${(err as Error).message}`, "error");
    } finally {
      setSaving(false);
    }
  };

  const handleGenerateAI = async () => {
    setAiGenerating(true);
    try {
      const res = await API.generateAIDescription(projectName, {
        type: "clue",
        name,
        description: description || name,
        model: textModel || undefined,
      });
      setDescription(res.prompt);
      useAppStore.getState().pushToast("提示詞生成成功", "success");
    } catch (err) {
      useAppStore.getState().pushToast(`AI 提示詞生成失敗: ${(err as Error).message}`, "error");
    } finally {
      setAiGenerating(false);
    }
  };

  const sheetUrl = clue.clue_sheet
    ? API.getFileUrl(projectName, clue.clue_sheet, sheetFp)
    : null;

  const savedReferenceUrl = clue.reference_image
    ? API.getFileUrl(projectName, clue.reference_image, referenceFp)
    : null;

  return (
    <div
      className="rounded-xl border border-gray-800 bg-gray-900 p-5"
      data-workspace-editing={isEditing || isDirty ? "true" : undefined}
      onFocusCapture={() => setIsEditing(true)}
      onBlurCapture={(event) => {
        const nextTarget = event.relatedTarget;
        if (nextTarget instanceof Node && event.currentTarget.contains(nextTarget)) {
          return;
        }
        setIsEditing(false);
      }}
    >
      {/* ---- Header: name + badges ---- */}
      <div className="mb-4 flex items-center gap-2">
        {renaming ? (
          <input
            type="text"
            autoFocus
            value={nameDraft}
            onChange={(e) => setNameDraft(e.target.value)}
            onBlur={() => void commitRename()}
            onKeyDown={(e) => {
              if (e.nativeEvent.isComposing) return;
              if (e.key === "Enter") {
                e.preventDefault();
                void commitRename();
              } else if (e.key === "Escape") {
                setNameDraft(name);
                setRenaming(false);
              }
            }}
            className="min-w-0 flex-1 rounded border border-indigo-500 bg-gray-800 px-2 py-0.5 text-lg font-bold text-white focus:outline-none"
            aria-label="道具名稱"
          />
        ) : (
          <button
            type="button"
            onClick={() => onRename && setRenaming(true)}
            disabled={!onRename}
            className="group flex min-w-0 flex-1 items-center gap-1.5 text-left disabled:cursor-default"
            title={onRename ? "點擊改名" : undefined}
          >
            <h3 className="truncate text-lg font-bold text-white">{name}</h3>
            {onRename && (
              <Pencil className="h-3 w-3 shrink-0 text-gray-600 opacity-0 transition-opacity group-hover:opacity-100" />
            )}
          </button>
        )}

        {clue.importance === "major" ? (
          <span className="shrink-0 rounded-full bg-indigo-500/10 px-2 py-0.5 text-xs font-medium text-indigo-400 border border-indigo-500/20">
            重要
          </span>
        ) : (
          <span className="shrink-0 rounded-full bg-gray-700 px-2 py-0.5 text-xs font-medium text-gray-400">
            次要
          </span>
        )}

        {onDelete && (
          <button
            type="button"
            onClick={async () => {
              const ok = await confirm({
                message: `確定要刪除道具「${name}」？此操作無法復原。`,
                danger: true,
              });
              if (ok) void onDelete(name);
            }}
            className="ml-auto shrink-0 rounded p-1.5 text-gray-500 transition-colors hover:bg-red-500/10 hover:text-red-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500/60"
            title="刪除"
            aria-label={`刪除道具 ${name}`}
          >
            <Trash2 className="h-4 w-4" />
          </button>
        )}
      </div>

      <div className="mb-4 space-y-3">
        {/* 提示詞 (描述) 與模型選擇 / AI 生成按鈕 */}
        <LorebookDescriptionField
          value={description}
          onChange={setDescription}
          placeholder="輸入道具描述..."
          onGenerateAI={handleGenerateAI}
          aiGenerating={aiGenerating}
          textModel={textModel}
          onTextModelChange={setTextModel}
          textModelOptions={modelOptions?.text ?? []}
          providerNames={modelOptions?.providerNames ?? {}}
        />

        {isDirty && (
          <button
            type="button"
            onClick={() => void handleSave()}
            disabled={saving}
            className="mt-3 w-full rounded-lg bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saving ? "儲存中..." : "儲存"}
          </button>
        )}
      </div>

      {/* 下面是圖跟模型選單與生圖的按鈕 */}
      <div className="mt-4 pt-4 border-t border-gray-800 space-y-3">
        <div>
          <div className="mb-1.5 flex items-center justify-between">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-gray-500">
              道具設計圖
            </span>
            <VersionTimeMachine
              projectName={projectName}
              resourceType="clues"
              resourceId={name}
              onRestore={onRestoreVersion}
            />
          </div>
          <PreviewableImageFrame
            src={sheetUrl && !imgError ? sheetUrl : null}
            alt={`${name} 設計圖`}
          >
            <AspectFrame ratio="16:9">
              {sheetUrl && !imgError ? (
                <img
                  src={sheetUrl}
                  alt={`${name} 設計圖`}
                  className="h-full w-full object-cover"
                  onError={() => setImgError(true)}
                />
              ) : (
                <div className="flex h-full w-full flex-col items-center justify-center gap-2 text-gray-500">
                  <Puzzle className="h-10 w-10" />
                  <span className="text-xs">暫無道具圖片</span>
                </div>
              )}
            </AspectFrame>
          </PreviewableImageFrame>
        </div>

        <LorebookReferenceImageField
          name={name}
          savedUrl={savedReferenceUrl}
          resetKey={savedReferenceUrl}
          onUpload={(file) => onUploadReference ? onUploadReference(name, file) : Promise.resolve()}
          onRemove={onRemoveReference ? () => onRemoveReference(name) : undefined}
        />

        <LorebookImageGenerateControls
          value={imageBackend}
          onChange={handleModelChange}
          options={modelOptions?.image}
          providerNames={modelOptions?.providerNames}
          onGenerate={() => onGenerate(name)}
          loading={generating}
          label={clue.clue_sheet ? "生成道具" : "生成道具"}
        />
      </div>
    </div>
  );
}
