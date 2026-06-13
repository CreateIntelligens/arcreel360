import { useEffect, useRef, useState } from "react";
import { ImagePlus, Upload, X } from "lucide-react";
import { PreviewableImageFrame } from "@/components/ui/PreviewableImageFrame";
import { useConfirm } from "@/hooks/useConfirm";

interface LorebookReferenceImageFieldProps {
  name: string;
  savedUrl: string | null;
  resetKey?: string | null;
  onUpload: (file: File) => Promise<void> | void;
  onRemove?: () => Promise<void> | void;
}

const REFERENCE_IMAGE_ACCEPT = ".png,.jpg,.jpeg,.webp";

function getReferenceStatusLabel(isUploading: boolean, hasPendingReference: boolean): string {
  if (isUploading) {
    return "上傳中...";
  }
  if (hasPendingReference) {
    return "已上傳參考圖";
  }
  return "已儲存參考圖";
}

export function LorebookReferenceImageField({
  name,
  savedUrl,
  resetKey,
  onUpload,
  onRemove,
}: LorebookReferenceImageFieldProps) {
  const [referencePreview, setReferencePreview] = useState<string | null>(null);
  const [savingReference, setSavingReference] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const confirm = useConfirm();

  useEffect(() => {
    setReferencePreview((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return null;
    });
  }, [resetKey]);

  useEffect(() => {
    return () => {
      if (referencePreview) {
        URL.revokeObjectURL(referencePreview);
      }
    };
  }, [referencePreview]);

  const displayedReferenceUrl = referencePreview ?? savedUrl;
  const openReferencePicker = () => fileInputRef.current?.click();
  const referenceStatusLabel = getReferenceStatusLabel(savingReference, referencePreview !== null);

  const handleReferenceChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;

    setReferencePreview((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return URL.createObjectURL(file);
    });
    setSavingReference(true);
    try {
      await onUpload(file);
    } finally {
      setSavingReference(false);
    }
  };

  const handleRemove = async () => {
    if (!onRemove) return;
    const ok = await confirm({
      message: `確定要移除「${name}」參考圖嗎？`,
      confirmLabel: "移除",
      danger: true,
    });
    if (!ok) return;

    try {
      await onRemove();
      setReferencePreview((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return null;
      });
    } catch (err) {
      console.error("Failed to remove reference image:", err);
    }
  };

  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wider text-gray-500">
          參考圖
        </span>
      </div>

      {displayedReferenceUrl ? (
        <PreviewableImageFrame
          src={displayedReferenceUrl}
          alt={`${name} 參考圖`}
          buttonClassName="left-2.5 right-auto top-2.5"
        >
          <div className="relative overflow-hidden rounded-lg border border-gray-700 bg-gray-800">
            <img
              src={displayedReferenceUrl}
              alt={`${name} 參考圖`}
              className="h-28 w-full object-cover"
            />
            {onRemove && (
              <button
                type="button"
                onClick={handleRemove}
                aria-label={`移除 ${name} 參考圖`}
                className="absolute right-2 top-2 z-10 inline-flex h-7 w-7 items-center justify-center rounded-full border border-white/10 bg-black/50 text-white/85 shadow-lg backdrop-blur transition-colors hover:bg-red-500/85 hover:text-white focus:outline-none focus:ring-2 focus:ring-red-300/70"
              >
                <X className="h-4 w-4" />
              </button>
            )}
            <div className="absolute inset-x-0 bottom-0 flex items-center justify-between bg-gradient-to-t from-black/70 to-transparent px-3 py-2">
              <span className="flex items-center gap-1.5 text-xs text-gray-200">
                <ImagePlus className="h-3.5 w-3.5" />
                {referenceStatusLabel}
              </span>
              <button
                type="button"
                onClick={openReferencePicker}
                aria-label="替換參考圖"
                className="rounded bg-black/40 px-2 py-1 text-xs text-gray-200 transition-colors hover:bg-black/60"
              >
                替換
              </button>
            </div>
          </div>
        </PreviewableImageFrame>
      ) : (
        <button
          type="button"
          onClick={openReferencePicker}
          className="flex h-28 w-full flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-gray-700 bg-gray-800/50 text-sm text-gray-500 transition-colors hover:border-gray-500 hover:text-gray-300"
        >
          <Upload className="h-6 w-6" />
          <span>上傳參考圖</span>
        </button>
      )}
      <input
        ref={fileInputRef}
        type="file"
        accept={REFERENCE_IMAGE_ACCEPT}
        onChange={handleReferenceChange}
        className="hidden"
      />
    </div>
  );
}
