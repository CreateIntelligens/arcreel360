import { useEffect, useState } from "react";
import { Pencil, Trash2, User } from "lucide-react";
import { API } from "@/api";
import { VersionTimeMachine } from "@/components/canvas/timeline/VersionTimeMachine";
import { AspectFrame } from "@/components/ui/AspectFrame";
import { ImageFlipReveal } from "@/components/ui/ImageFlipReveal";
import { PreviewableImageFrame } from "@/components/ui/PreviewableImageFrame";
import { useProjectsStore } from "@/stores/projects-store";
import { useAppStore } from "@/stores/app-store";
import { useConfirm } from "@/hooks/useConfirm";
import type { Character } from "@/types";
import { LorebookDescriptionField } from "./LorebookDescriptionField";
import { LorebookImageGenerateControls } from "./LorebookImageGenerateControls";
import { LorebookReferenceImageField } from "./LorebookReferenceImageField";

interface CharacterSavePayload {
  description: string;
  voiceStyle: string;
  imageBackend?: string | null;
}

interface CharacterCardProps {
  name: string;
  character: Character;
  projectName: string;
  onSave: (name: string, payload: CharacterSavePayload) => Promise<void>;
  onUploadReference: (name: string, file: File) => Promise<void> | void;
  onRemoveReference?: (name: string) => Promise<void> | void;
  onGenerate: (name: string) => void;
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

export function CharacterCard({
  name,
  character,
  projectName,
  onSave,
  onUploadReference,
  onRemoveReference,
  onGenerate,
  onDelete,
  onRename,
  onRestoreVersion,
  generating = false,
  modelOptions,
}: CharacterCardProps) {
  const confirm = useConfirm();
  const [isEditing, setIsEditing] = useState(false);
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
    (s) => character.character_sheet ? s.getAssetFingerprint(character.character_sheet) : null,
  );
  const referenceFp = useProjectsStore(
    (s) => character.reference_image ? s.getAssetFingerprint(character.reference_image) : null,
  );
  const [description, setDescription] = useState(character.description);
  const [voiceStyle, setVoiceStyle] = useState(character.voice_style ?? "");
  const [imageBackend, setImageBackend] = useState(character.image_backend ?? "");
  const [imgError, setImgError] = useState(false);
  const [saving, setSaving] = useState(false);
  const [aiGenerating, setAiGenerating] = useState(false);

  useEffect(() => {
    setDescription(character.description);
    setVoiceStyle(character.voice_style ?? "");
    setImageBackend(character.image_backend ?? "");
  }, [character.description, character.voice_style, character.image_backend]);

  useEffect(() => {
    setImgError(false);
  }, [character.character_sheet, sheetFp]);

  const isDirty =
    description !== character.description ||
    voiceStyle !== (character.voice_style ?? "") ||
    imageBackend !== (character.image_backend ?? "");

  const handleSave = async () => {
    setSaving(true);
    try {
      await onSave(name, {
        description,
        voiceStyle,
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
        voiceStyle,
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
        type: "character",
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

  const sheetUrl = character.character_sheet
    ? API.getFileUrl(projectName, character.character_sheet, sheetFp)
    : null;

  const savedReferenceUrl = character.reference_image
    ? API.getFileUrl(projectName, character.reference_image, referenceFp)
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
      <div className="mb-4 flex items-center justify-between gap-2">
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
            className="flex-1 rounded border border-indigo-500 bg-gray-800 px-2 py-0.5 text-lg font-bold text-white focus:outline-none"
            aria-label="角色名稱"
          />
        ) : (
          <button
            type="button"
            onClick={() => onRename && setRenaming(true)}
            disabled={!onRename}
            className="group flex flex-1 min-w-0 items-center gap-1.5 text-left disabled:cursor-default"
            title={onRename ? "點擊改名" : undefined}
          >
            <h3 className="truncate text-lg font-bold text-white">{name}</h3>
            {onRename && (
              <Pencil className="h-3 w-3 shrink-0 text-gray-600 opacity-0 transition-opacity group-hover:opacity-100" />
            )}
          </button>
        )}
        {onDelete && (
          <button
            type="button"
            onClick={async () => {
              const ok = await confirm({
                message: `確定要刪除角色「${name}」？此操作無法復原。`,
                danger: true,
              });
              if (ok) void onDelete(name);
            }}
            className="shrink-0 rounded p-1.5 text-gray-500 transition-colors hover:bg-red-500/10 hover:text-red-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500/60"
            title="刪除角色"
            aria-label={`刪除角色 ${name}`}
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
          placeholder="輸入角色描述..."
          onGenerateAI={handleGenerateAI}
          aiGenerating={aiGenerating}
          textModel={textModel}
          onTextModelChange={setTextModel}
          textModelOptions={modelOptions?.text ?? []}
          providerNames={modelOptions?.providerNames ?? {}}
        />

        <label className="block text-xs font-medium text-gray-400">聲音風格</label>
        <input
          type="text"
          value={voiceStyle}
          onChange={(e) => setVoiceStyle(e.target.value)}
          className="mt-1 w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:border-indigo-500 focus:outline-none"
          placeholder="例如：溫柔但有威嚴"
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
              角色設計圖
            </span>
            <VersionTimeMachine
              projectName={projectName}
              resourceType="characters"
              resourceId={name}
              onRestore={onRestoreVersion}
            />
          </div>
          <PreviewableImageFrame
            src={sheetUrl && !imgError ? sheetUrl : null}
            alt={`${name} 設計圖`}
          >
            <AspectFrame ratio="3:4">
              <ImageFlipReveal
                src={sheetUrl && !imgError ? sheetUrl : null}
                alt={`${name} 設計圖`}
                className="h-full w-full object-cover"
                onError={() => setImgError(true)}
                fallback={
                  <div className="flex h-full w-full flex-col items-center justify-center gap-2 text-gray-500">
                    <User className="h-10 w-10" />
                    <span className="text-xs">暫無角色圖片</span>
                  </div>
                }
              />
            </AspectFrame>
          </PreviewableImageFrame>
        </div>

        <LorebookReferenceImageField
          name={name}
          savedUrl={savedReferenceUrl}
          resetKey={savedReferenceUrl}
          onUpload={(file) => onUploadReference(name, file)}
          onRemove={onRemoveReference ? () => onRemoveReference(name) : undefined}
        />

        <LorebookImageGenerateControls
          value={imageBackend}
          onChange={handleModelChange}
          options={modelOptions?.image}
          providerNames={modelOptions?.providerNames}
          onGenerate={() => onGenerate(name)}
          loading={generating}
          label={character.character_sheet ? "生成角色" : "生成角色"}
        />
      </div>
    </div>
  );
}
