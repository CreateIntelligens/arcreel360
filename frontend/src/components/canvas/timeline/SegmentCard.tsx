import { useCallback, useEffect, useMemo, useState } from "react";
import { Monitor, ImageIcon, Trash2 } from "lucide-react";
import {
  coerceDurationToOptions,
  DEFAULT_DURATIONS,
  DEFAULT_RESOLUTIONS,
  DEFAULT_IMAGE_SIZES,
  getDurationConstraintReason,
} from "@/utils/provider-models";
import { useGlobalModelDefaults } from "@/hooks/useGlobalModelDefaults";
import { useImageSizeOptions } from "@/hooks/useImageSizeOptions";
import { useVideoResolutionOptions } from "@/hooks/useVideoResolutionOptions";
import { useVideoDurationOptions } from "@/hooks/useVideoDurationOptions";
import { useCostStore } from "@/stores/cost-store";
import { useAppStore } from "@/stores/app-store";
import { formatCost } from "@/utils/cost-format";
import { AvatarStack } from "@/components/ui/AvatarStack";
import { ClueStack } from "@/components/ui/ClueStack";
import { ProviderModelSelect } from "@/components/ui/ProviderModelSelect";
import { extractEntityMentionsFromValue, type EntityMentionSources } from "@/utils/entity-mentions";
import type { SegmentCost } from "@/types";

import type {
  SegmentCardProps,
  SegmentMentionDrafts,
  SegmentMentionDraftKey,
  SegmentUpdateExtras,
} from "./segment-card/types";
import {
  getSegmentId,
  getCharacterNames,
  getClueNames,
  getSceneName,
  getSourceMentionValue,
  getSegmentMentionDrafts,
  getMentionDraftValues,
  buildMentionFieldUpdates,
} from "./segment-card/helpers";
import { DurationSelector } from "./segment-card/DurationSelector";
import { OptionPillSelector, SegmentBreakSeparator, TransitionIndicator } from "./segment-card/TransitionIndicator";
import { TextColumn } from "./segment-card/TextColumn";
import { PromptColumn } from "./segment-card/PromptColumn";
import { MediaColumn } from "./segment-card/MediaColumn";

export type { SegmentCardProps };

type MediaCostKind = "image" | "video";

const MEDIA_COST_LABELS: Record<MediaCostKind, string> = {
  image: "分鏡",
  video: "影片",
};

function getVisibleCostKinds(stage: SegmentCardProps["stage"]): MediaCostKind[] {
  if (stage === "storyboard") return ["image"];
  if (stage === "video") return ["video"];
  return ["image", "video"];
}

function SegmentCostSummary({
  cost,
  kinds,
}: {
  cost: SegmentCost | undefined;
  kinds: MediaCostKind[];
}) {
  if (!cost) return null;

  return (
    <span className="inline-flex items-center gap-1.5 tabular-nums text-xs">
      <span className="text-gray-700">|</span>
      <span className="text-gray-600">預估</span>
      {kinds.map((kind) => (
        <span key={`estimate-${kind}`} className="text-gray-500">
          {MEDIA_COST_LABELS[kind]} <span className="text-gray-400">{formatCost(cost.estimate[kind])}</span>
        </span>
      ))}
      <span className="text-gray-700">|</span>
      <span className="text-gray-600">實際</span>
      {kinds.map((kind) => (
        <span key={`actual-${kind}`} className="text-gray-500">
          {MEDIA_COST_LABELS[kind]} <span className="text-gray-400">{formatCost(cost.actual[kind])}</span>
        </span>
      ))}
    </span>
  );
}

function pushDurationAdjustmentToast(previous: number, next: number, reason?: string) {
  if (!reason) return;
  useAppStore
    .getState()
    .pushToast(`已自動將秒數從 ${previous} 調整為 ${next}（${reason}）`, "warning");
}

export function SegmentCard({
  segment,
  contentMode,
  aspectRatio,
  characters,
  clues,
  scenes = {},
  projectName,
  episode,
  scriptFile,
  videoBackend,
  currentResolution,
  durationOptions,
  durationConstraintReason,
  onUpdatePrompt,
  onGenerateStoryboard,
  onGenerateVideo,
  onRestoreStoryboard,
  onRestoreVideo,
  onDelete,
  generatingStoryboard = false,
  generatingVideo = false,
  onUploadReference,
  onRemoveReference,
  stage,
  imageModelOptions = [],
  videoModelOptions = [],
  textModelOptions = [],
  providerNames = {},
  styleContext,
  onUpdateSceneBackend,
}: SegmentCardProps) {
  const segmentId = getSegmentId(segment, contentMode);
  const segCost = useCostStore((s) => s.getSegmentCost(segmentId));
  const charNames = getCharacterNames(segment, contentMode);
  const clueNames = getClueNames(segment, contentMode);
  const sceneName = getSceneName(segment, contentMode);
  const mentionEntities = useMemo<EntityMentionSources>(
    () => ({
      characters,
      clues,
      scenes,
    }),
    [characters, clues, scenes],
  );
  const [mentionDrafts, setMentionDrafts] = useState<SegmentMentionDrafts>(() =>
    getSegmentMentionDrafts(segment, contentMode)
  );
  const sourceMentionValue = getSourceMentionValue(segment, contentMode);
  const showStoryboardControls = stage === undefined || stage === "storyboard";
  const showVideoControls = stage === undefined || stage === "video";
  const visibleCostKinds = useMemo(() => getVisibleCostKinds(stage), [stage]);

  useEffect(() => {
    setMentionDrafts(getSegmentMentionDrafts(segment, contentMode));
  }, [
    segmentId,
    contentMode,
    sourceMentionValue,
    segment.image_prompt,
    segment.video_prompt,
  ]);

  const onMentionDraftChange = useCallback((key: SegmentMentionDraftKey, value: unknown) => {
    setMentionDrafts((prev) => {
      if (Object.is(prev[key], value)) {
        return prev;
      }
      return { ...prev, [key]: value };
    });
  }, []);

  const mentionContext = useMemo(
    () => ({
      contentMode,
      currentNames: {
        characterNames: charNames,
        clueNames,
        sceneName,
      },
      entities: mentionEntities,
    }),
    [charNames, clueNames, contentMode, mentionEntities, sceneName],
  );

  const buildMentionUpdatesForDraft = useCallback(
    (patch: Partial<SegmentMentionDrafts>): SegmentUpdateExtras | undefined => {
      const nextDrafts = { ...mentionDrafts, ...patch };
      return buildMentionFieldUpdates(getMentionDraftValues(nextDrafts), mentionContext);
    },
    [mentionContext, mentionDrafts],
  );

  const { characterNames: liveCharNames, clueNames: liveClueNames } = useMemo(
    () => extractEntityMentionsFromValue(getMentionDraftValues(mentionDrafts), mentionEntities),
    [mentionDrafts, mentionEntities],
  );
  const hasReferenceImage = Boolean(segment.generated_assets?.storyboard_image);

  const globalDefaults = useGlobalModelDefaults();
  // Per-scene overrides take precedence over the project-level props.
  const effectiveVideoBackend = segment.video_backend || videoBackend;
  const effectiveImageBackend = segment.image_backend || undefined;
  const effectiveResolution = segment.video_resolution ?? currentResolution ?? null;

  const resolutionOptions = useVideoResolutionOptions(effectiveVideoBackend) ?? DEFAULT_RESOLUTIONS;
  const imageSizeOptions = useImageSizeOptions(effectiveImageBackend) ?? DEFAULT_IMAGE_SIZES;
  const currentImageSize = segment.image_size ?? imageSizeOptions[0] ?? DEFAULT_IMAGE_SIZES[0];
  const currentVideoResolution =
    effectiveResolution ?? resolutionOptions[0] ?? DEFAULT_RESOLUTIONS[0];

  const dynamicDurationOptions = useVideoDurationOptions(effectiveVideoBackend, {
    currentResolution: effectiveResolution,
    hasReferenceImage,
  });
  const effectiveDurationOptions = dynamicDurationOptions ?? durationOptions ?? (DEFAULT_DURATIONS as number[]);
  const effectiveDurationReason =
    durationConstraintReason ??
    getDurationConstraintReason({ currentResolution: effectiveResolution, hasReferenceImage });

  useEffect(() => {
    if (!showVideoControls) return;
    if (!onUpdatePrompt || effectiveDurationOptions.includes(segment.duration_seconds)) return;
    const nextDuration = coerceDurationToOptions(segment.duration_seconds, effectiveDurationOptions);
    if (nextDuration === segment.duration_seconds) return;

    onUpdatePrompt(segmentId, "duration_seconds", nextDuration);
    pushDurationAdjustmentToast(segment.duration_seconds, nextDuration, effectiveDurationReason);
  }, [
    effectiveDurationOptions,
    effectiveDurationReason,
    onUpdatePrompt,
    segment.duration_seconds,
    segmentId,
    showVideoControls,
  ]);

  return (
    <div>
      {/* Segment break separator */}
      {segment.segment_break && <SegmentBreakSeparator />}

      {/* Main card */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        {/* ---- Header ---- */}
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-800">
          {/* Left: ID badge + duration */}
          <div className="flex items-center gap-2">
            <span className="font-mono text-xs bg-gray-800 rounded px-1.5 py-0.5 text-gray-300">
              {segmentId}
            </span>
            {showVideoControls && (
              <>
                <DurationSelector
                  seconds={segment.duration_seconds}
                  segmentId={segmentId}
                  onUpdatePrompt={onUpdatePrompt}
                  durationOptions={effectiveDurationOptions}
                  durationConstraintReason={effectiveDurationReason}
                />
                <OptionPillSelector
                  value={currentVideoResolution}
                  options={resolutionOptions}
                  icon={<Monitor aria-hidden="true" className="h-3 w-3" />}
                  ariaLabel="影片解析度選擇"
                  onSelect={
                    onUpdatePrompt
                      ? (next) => onUpdatePrompt(segmentId, "video_resolution", next)
                      : undefined
                  }
                />
              </>
            )}
            {stage === "video" && videoModelOptions.length > 0 && (
              <ProviderModelSelect
                value={segment.video_backend ?? ""}
                options={videoModelOptions}
                providerNames={providerNames}
                onChange={(next) => onUpdateSceneBackend?.(segmentId, { video_backend: next || null })}
                allowDefault
                defaultLabel="專案預設模型"
                defaultModelValue={videoBackend || globalDefaults.video}
                aria-label="選擇分鏡影片模型"
                className="w-44"
              />
            )}
            {showStoryboardControls && (
              <OptionPillSelector
                value={currentImageSize}
                options={imageSizeOptions}
                icon={<ImageIcon aria-hidden="true" className="h-3 w-3" />}
                ariaLabel="圖片解析度選擇"
                onSelect={
                  onUpdatePrompt
                    ? (next) => onUpdatePrompt(segmentId, "image_size", next)
                    : undefined
                }
              />
            )}
            <SegmentCostSummary cost={segCost} kinds={visibleCostKinds} />
          </div>

          {/* Right: AvatarStack + ClueStack */}
          <div className="flex items-center gap-2">
            <AvatarStack
              names={liveCharNames}
              characters={characters}
              projectName={projectName}
            />
            {liveCharNames.length > 0 && liveClueNames.length > 0 && (
              <div className="border-l border-gray-700 self-stretch" />
            )}
            <ClueStack
              names={liveClueNames}
              clues={clues}
              projectName={projectName}
            />
            {onDelete && (
              <button
                type="button"
                onClick={onDelete}
                title={`刪除${contentMode === "narration" ? "片段" : "場景"}`}
                aria-label={`刪除${contentMode === "narration" ? "片段" : "場景"}`}
                className="ml-1 rounded p-1 text-gray-600 transition-colors hover:bg-red-500/10 hover:text-red-400"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
        </div>

        {/* ---- Content: three-column grid ---- */}
        <div className="grid grid-cols-3 gap-0 divide-x divide-gray-800">
          {/* Column 1 — Text */}
          <TextColumn
            segment={segment}
            contentMode={contentMode}
            mentionContext={mentionContext}
            onMentionDraftChange={onMentionDraftChange}
            buildMentionUpdatesForDraft={buildMentionUpdatesForDraft}
            onUpdateNote={(value) => onUpdatePrompt?.(segmentId, "note", value)}
            onUpdateSourceText={(value, extraUpdates) =>
              onUpdatePrompt?.(
                segmentId,
                contentMode === "narration" ? "novel_text" : "scene_description",
                value,
                extraUpdates,
              )
            }
          />

          {/* Column 2 — Prompts */}
          <PromptColumn
            segment={segment}
            segmentId={segmentId}
            projectName={projectName}
            onUpdatePrompt={onUpdatePrompt}
            speakerOptions={charNames}
            mentionContext={mentionContext}
            onMentionDraftChange={onMentionDraftChange}
            buildMentionUpdatesForDraft={buildMentionUpdatesForDraft}
            sourceDraft={mentionDrafts.source}
            stage={stage}
            textModelOptions={textModelOptions}
            providerNames={providerNames}
            styleContext={styleContext}
          />

          {/* Column 3 — Media */}
          <MediaColumn
            segment={segment}
            aspectRatio={aspectRatio}
            projectName={projectName}
            segmentId={segmentId}
            onGenerateStoryboard={onGenerateStoryboard}
            onGenerateVideo={onGenerateVideo}
            onRestoreStoryboard={onRestoreStoryboard}
            onRestoreVideo={onRestoreVideo}
            generatingStoryboard={generatingStoryboard}
            generatingVideo={generatingVideo}
            onUploadReference={onUploadReference}
            onRemoveReference={onRemoveReference}
            stage={stage}
            imageModelOptions={imageModelOptions}
            providerNames={providerNames}
            onUpdateSceneBackend={onUpdateSceneBackend}
          />
        </div>
      </div>

      {/* Transition indicator to next card */}
      <TransitionIndicator type={segment.transition_to_next} />
    </div>
  );
}
