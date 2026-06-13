import { useState, useRef } from "react";
import { ImageIcon, Film, Upload } from "lucide-react";
import { API } from "@/api";
import { useProjectsStore } from "@/stores/projects-store";
import { useConfirm } from "@/hooks/useConfirm";
import { VersionTimeMachine } from "@/components/canvas/timeline/VersionTimeMachine";
import { AspectFrame } from "@/components/ui/AspectFrame";
import { GenerateButton } from "@/components/ui/GenerateButton";
import { ImageFlipReveal } from "@/components/ui/ImageFlipReveal";
import { ProviderModelSelect } from "@/components/ui/ProviderModelSelect";
import { PreviewableImageFrame } from "@/components/ui/PreviewableImageFrame";
import { PreviewableVideoFrame } from "@/components/ui/PreviewableVideoFrame";
import { modelSelectRowClasses } from "@/utils/model-select-row";
import { useGlobalModelDefaults } from "@/hooks/useGlobalModelDefaults";
import type { Segment } from "./types";

interface MediaColumnProps {
  segment: Segment;
  aspectRatio: string;
  projectName: string;
  segmentId: string;
  onGenerateStoryboard?: (segmentId: string) => void;
  onGenerateVideo?: (segmentId: string) => void;
  onRestoreStoryboard?: () => Promise<void> | void;
  onRestoreVideo?: () => Promise<void> | void;
  generatingStoryboard?: boolean;
  generatingVideo?: boolean;
  onUploadReference?: (segmentId: string, file: File) => Promise<void> | void;
  onRemoveReference?: (segmentId: string) => Promise<void> | void;
  stage?: "storyboard" | "video";
  imageModelOptions?: string[];
  providerNames?: Record<string, string>;
  onUpdateSceneBackend?: (
    segmentId: string,
    patch: { image_backend?: string | null; video_backend?: string | null }
  ) => Promise<void> | void;
}

/** Simple video player with poster thumbnail and lazy preload. */
function VideoPlayer({ src, poster }: { src: string; poster?: string | null }) {
  return (
    <video
      src={src}
      poster={poster ?? undefined}
      className="h-full w-full bg-black object-contain"
      controls
      playsInline
      preload={poster ? "none" : "metadata"}
    />
  );
}

interface CompactReferenceImageFieldProps {
  name: string;
  savedUrl: string | null;
  onUpload: (file: File) => Promise<void> | void;
  onRemove?: () => Promise<void> | void;
}

function CompactReferenceImageField({
  name,
  savedUrl,
  onUpload,
  onRemove,
}: CompactReferenceImageFieldProps) {
  const [saving, setSaving] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const confirm = useConfirm();

  const openPicker = () => fileInputRef.current?.click();

  const handleChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setSaving(true);
    try {
      await onUpload(file);
    } finally {
      setSaving(false);
    }
  };

  const handleRemove = async () => {
    if (!onRemove) return;
    const ok = await confirm({
      message: `確定要移除分鏡參考圖嗎？`,
      confirmLabel: "移除",
      danger: true,
    });
    if (ok) {
      await onRemove();
    }
  };

  return (
    <div>
      {savedUrl ? (
        <PreviewableImageFrame src={savedUrl} alt={`${name} 參考圖`}>
          <div className="flex items-center gap-2 rounded-lg border border-gray-800 bg-gray-900/40 p-2 text-xs text-gray-400">
            <div className="h-10 w-10 shrink-0 overflow-hidden rounded bg-gray-950">
              <img src={savedUrl} alt="分鏡參考圖" className="h-full w-full object-cover" />
            </div>
            <div className="flex-1 flex flex-col gap-0.5">
              <span className="font-medium text-gray-300">分鏡參考圖</span>
              <div className="flex items-center gap-2 text-[10px]">
                <button
                  type="button"
                  disabled={saving}
                  onClick={openPicker}
                  className="text-indigo-400 hover:text-indigo-300 disabled:opacity-50"
                >
                  {saving ? "上傳中..." : "替換"}
                </button>
                {onRemove && (
                  <>
                    <span className="text-gray-700">|</span>
                    <button
                      type="button"
                      onClick={handleRemove}
                      className="text-red-400/80 hover:text-red-400"
                    >
                      移除
                    </button>
                  </>
                )}
              </div>
            </div>
          </div>
        </PreviewableImageFrame>
      ) : (
        <button
          type="button"
          disabled={saving}
          onClick={openPicker}
          className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-dashed border-gray-700 bg-gray-800/30 py-2 text-[11px] text-gray-500 hover:border-gray-500 hover:text-gray-300 transition-colors"
        >
          <Upload className="h-3.5 w-3.5" />
          {saving ? "上傳中..." : "上傳參考圖"}
        </button>
      )}
      <input
        ref={fileInputRef}
        type="file"
        accept=".png,.jpg,.jpeg,.webp"
        onChange={handleChange}
        className="hidden"
      />
    </div>
  );
}

export function MediaColumn({
  segment,
  aspectRatio,
  projectName,
  segmentId,
  onGenerateStoryboard,
  onGenerateVideo,
  onRestoreStoryboard,
  onRestoreVideo,
  generatingStoryboard,
  generatingVideo,
  onUploadReference,
  onRemoveReference,
  stage,
  imageModelOptions = [],
  providerNames = {},
  onUpdateSceneBackend,
}: MediaColumnProps) {
  const assets = segment.generated_assets;
  const storyboardFp = useProjectsStore(
    (s) => assets?.storyboard_image ? s.getAssetFingerprint(assets.storyboard_image) : null,
  );
  const videoFp = useProjectsStore(
    (s) => assets?.video_clip ? s.getAssetFingerprint(assets.video_clip) : null,
  );
  const thumbnailFp = useProjectsStore(
    (s) => assets?.video_thumbnail ? s.getAssetFingerprint(assets.video_thumbnail) : null,
  );
  const refImageFp = useProjectsStore(
    (s) => segment.reference_image ? s.getAssetFingerprint(segment.reference_image) : null,
  );
  const storyboardUrl = assets?.storyboard_image
    ? API.getFileUrl(projectName, assets.storyboard_image, storyboardFp)
    : null;
  const refImageUrl = segment.reference_image
    ? API.getFileUrl(projectName, segment.reference_image, refImageFp)
    : null;
  const videoUrl = assets?.video_clip
    ? API.getFileUrl(projectName, assets.video_clip, videoFp)
    : null;
  const thumbnailUrl = assets?.video_thumbnail
    ? API.getFileUrl(projectName, assets.video_thumbnail, thumbnailFp)
    : null;

  // Normalize aspect ratio to the union type expected by AspectFrame
  const normalizedRatio = (
    aspectRatio === "9:16" || aspectRatio === "16:9" ? aspectRatio : "16:9"
  ) as "9:16" | "16:9";

  const mediaFrameMaxWidthClass = normalizedRatio === "9:16" ? "max-w-[10rem]" : "max-w-[18rem]";
  const globalDefaults = useGlobalModelDefaults();
  const showStoryboardModelSelect = stage === "storyboard" && imageModelOptions.length > 0;
  const storyboardRowClasses = modelSelectRowClasses(showStoryboardModelSelect, "mt-2");
  const storyboardToolbarClassName = storyboardRowClasses.container;
  const storyboardButtonClassName = storyboardRowClasses.button;

  return (
    <div className="flex flex-col gap-3 p-3">
      {/* ---- Storyboard image ---- */}
      {(stage === undefined || stage === "storyboard") && (
        <div data-testid="storyboard-media-frame" className={`mx-auto w-full ${mediaFrameMaxWidthClass}`}>
          <div className="mb-1.5 flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <ImageIcon className="h-3 w-3 text-gray-500" />
              <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-500">分鏡圖</span>
            </div>
            <VersionTimeMachine
              projectName={projectName}
              resourceType="storyboards"
              resourceId={segmentId}
              onRestore={onRestoreStoryboard}
            />
          </div>
          <PreviewableImageFrame src={storyboardUrl} alt={`${segmentId} 分鏡圖`}>
            <AspectFrame ratio={normalizedRatio}>
              <ImageFlipReveal
                src={storyboardUrl}
                alt={`${segmentId} 分鏡圖`}
                loading="lazy"
                className="h-full w-full object-cover"
                fallback={
                  <div className="flex h-full w-full flex-col items-center justify-center gap-2 text-gray-600">
                    <ImageIcon className="h-8 w-8" />
                    <span className="text-xs">暫無分鏡</span>
                  </div>
                }
              />
            </AspectFrame>
          </PreviewableImageFrame>
          <div
            data-testid="storyboard-generate-toolbar"
            className={storyboardToolbarClassName}
          >
            {showStoryboardModelSelect && (
              <div className={storyboardRowClasses.select}>
                <ProviderModelSelect
                  value={segment.image_backend ?? ""}
                  options={imageModelOptions}
                  providerNames={providerNames}
                  onChange={(next) => onUpdateSceneBackend?.(segmentId, { image_backend: next || null })}
                  allowDefault
                  defaultLabel="專案預設模型"
                  defaultModelValue={globalDefaults.image}
                  placeholder="選擇圖片模型..."
                  aria-label="選擇分鏡圖圖片模型"
                  className="w-full text-xs"
                  size="sm"
                />
              </div>
            )}
            <GenerateButton
              onClick={() => onGenerateStoryboard?.(segmentId)}
              loading={generatingStoryboard}
              label="生圖"
              className={storyboardButtonClassName}
            />
          </div>
          {onUploadReference && (
            <div className="mt-3">
              <CompactReferenceImageField
                name={segmentId}
                savedUrl={refImageUrl}
                onUpload={(file) => onUploadReference(segmentId, file)}
                onRemove={onRemoveReference ? () => onRemoveReference(segmentId) : undefined}
              />
            </div>
          )}
        </div>
      )}

      {/* ---- Video ---- */}
      {(stage === undefined || stage === "video") && (
        <div data-testid="video-media-frame" className={`mx-auto w-full ${mediaFrameMaxWidthClass}`}>
          <div className="mb-1.5 flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <Film className="h-3 w-3 text-gray-500" />
              <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-500">影片</span>
            </div>
            <VersionTimeMachine
              projectName={projectName}
              resourceType="videos"
              resourceId={segmentId}
              onRestore={onRestoreVideo}
            />
          </div>
          {videoUrl ? (
            <PreviewableVideoFrame src={videoUrl} poster={thumbnailUrl} alt={`${segmentId} 影片`}>
              <AspectFrame ratio={normalizedRatio}>
                <VideoPlayer src={videoUrl} poster={thumbnailUrl} />
              </AspectFrame>
            </PreviewableVideoFrame>
          ) : (
            <AspectFrame ratio={normalizedRatio}>
              <div className="flex h-full w-full flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-gray-700 bg-gray-800/30 text-gray-600">
                {storyboardUrl ? (
                  <div className="relative h-full w-full overflow-hidden rounded-lg">
                    <img src={storyboardUrl} alt="分鏡預覽" className="h-full w-full object-cover opacity-30 blur-[1px]" />
                    <div className="absolute inset-0 flex flex-col items-center justify-center gap-1.5 bg-black/40">
                      <Film className="h-7 w-7 text-gray-500" />
                      <span className="text-xs font-medium text-gray-400">暫無影片</span>
                    </div>
                  </div>
                ) : (
                  <>
                    <Film className="h-7 w-7 text-gray-600" />
                    <span className="text-xs">暫無影片</span>
                  </>
                )}
              </div>
            </AspectFrame>
          )}
          <div className="mt-2">
            <GenerateButton
              onClick={() => onGenerateVideo?.(segmentId)}
              loading={generatingVideo}
              label="生成影片"
              className="w-full justify-center"
              disabled={!assets?.storyboard_image}
            />
          </div>
        </div>
      )}
    </div>
  );
}
