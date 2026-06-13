import { useEffect, useMemo, useRef, useState } from "react";
import { ImageIcon, Film, Loader2 } from "lucide-react";
import { ProviderModelSelect } from "@/components/ui/ProviderModelSelect";
import { API } from "@/api";
import { useAppStore } from "@/stores/app-store";
import { useGlobalModelDefaults } from "@/hooks/useGlobalModelDefaults";
import { AutoTextarea } from "@/components/ui/AutoTextarea";
import { ImagePromptEditor } from "../ImagePromptEditor";
import { VideoPromptEditor } from "../VideoPromptEditor";
import type { ImagePrompt, VideoPrompt, NarrationSegment, DramaScene } from "@/types";
import type {
  Segment,
  SegmentMentionDrafts,
  SegmentMentionDraftKey,
  PromptMentionDraftKey,
  SegmentStyleContext,
  SegmentUpdateExtras,
  SegmentUpdateHandler,
} from "./types";
import {
  isStructuredImagePromptValue,
  isStructuredVideoPromptValue,
  mergePromptPatch,
  type SegmentMentionContext,
} from "./helpers";

function promptToStr(prompt: unknown, key: string): string {
  if (typeof prompt === "string") return prompt;
  if (typeof prompt === "object" && prompt !== null) {
    const value = (prompt as Record<string, unknown>)[key];
    if (typeof value === "string") return value;
  }
  return "";
}

function getPromptSourceText(
  segment: Segment,
  contentMode: SegmentMentionContext["contentMode"],
  sourceDraft?: unknown,
): string {
  const draftSource = typeof sourceDraft === "string" ? sourceDraft.trim() : undefined;
  if (contentMode === "narration") {
    return draftSource ?? (segment as NarrationSegment).novel_text ?? "";
  }

  const scene = segment as DramaScene;
  const prompt = scene.video_prompt;
  const sceneDescription = draftSource ?? scene.scene_description?.trim() ?? "";
  const narrationText = scene.narration_text?.trim() ?? "";
  const dialogueList = typeof prompt === "object" && prompt !== null && "dialogue" in prompt
    ? (prompt.dialogue as Array<{ speaker?: string; line?: string; text?: string }> ?? [])
    : [];
  const dialogueText = dialogueList
    .map((dialogue) => {
      const line = (dialogue.line ?? dialogue.text ?? "").trim();
      return line ? `${dialogue.speaker || "角色"}: ${line}` : "";
    })
    .filter(Boolean)
    .join("\n");
  const parts = [
    sceneDescription ? `場景描述:\n${sceneDescription}` : "",
    narrationText ? `旁白:\n${narrationText}` : "",
    scene.scene_in_scene ? `場景: ${scene.scene_in_scene}` : "",
    dialogueText ? `對話:\n${dialogueText}` : "",
    scene.note ? `備註: ${scene.note}` : "",
  ].filter(Boolean);
  return parts.join("\n");
}

function textValue(value: string | null | undefined): string {
  return typeof value === "string" ? value.trim() : "";
}

function buildReferenceContext(
  segment: Segment,
  styleContext?: SegmentStyleContext,
): string {
  const parts: string[] = [];
  const style = textValue(styleContext?.style);
  const styleDescription = textValue(styleContext?.styleDescription);
  const styleImage = textValue(styleContext?.styleImage);
  const referenceImage = textValue(segment.reference_image ?? null);

  if (style) parts.push(`專案風格: ${style}`);
  if (styleDescription) parts.push(`風格描述:\n${styleDescription}`);
  if (styleImage) parts.push(`風格參考圖: ${styleImage}`);
  if (referenceImage) parts.push(`分鏡參考圖: ${referenceImage}`);
  return parts.join("\n");
}

function withReferenceContext(baseDescription: string, referenceContext: string): string {
  return [baseDescription.trim(), referenceContext].filter(Boolean).join("\n");
}

interface PromptColumnProps {
  segment: Segment;
  segmentId: string;
  projectName: string;
  onUpdatePrompt?: SegmentUpdateHandler;
  speakerOptions?: string[];
  mentionContext: SegmentMentionContext;
  onMentionDraftChange: (key: SegmentMentionDraftKey, value: unknown) => void;
  buildMentionUpdatesForDraft: (
    patch: Partial<SegmentMentionDrafts>,
  ) => SegmentUpdateExtras | undefined;
  sourceDraft?: unknown;
  stage?: "storyboard" | "video";
  textModelOptions?: string[];
  providerNames?: Record<string, string>;
  styleContext?: SegmentStyleContext;
}

export function PromptColumn({
  segment,
  segmentId,
  projectName,
  onUpdatePrompt,
  speakerOptions,
  mentionContext,
  onMentionDraftChange,
  buildMentionUpdatesForDraft,
  sourceDraft,
  stage,
  textModelOptions,
  providerNames,
  styleContext,
}: PromptColumnProps) {
  const { image_prompt, video_prompt } = segment;
  const [textModel, setTextModel] = useState<string | null>(null);
  const buildPromptMentionUpdates = (
    key: PromptMentionDraftKey,
    value: unknown,
  ) => buildMentionUpdatesForDraft({ [key]: value });

  const isStructuredImage = isStructuredImagePromptValue(image_prompt);
  const isStructuredVideo = isStructuredVideoPromptValue(video_prompt);

  const [imgText, setImgText] = useState(() => promptToStr(image_prompt, "scene"));
  const [vidText, setVidText] = useState(() => promptToStr(video_prompt, "action"));
  const [imgDraft, setImgDraft] = useState<ImagePrompt | null>(() =>
    isStructuredImage ? (image_prompt as ImagePrompt) : null
  );
  const [vidDraft, setVidDraft] = useState<VideoPrompt | null>(() =>
    isStructuredVideo ? (video_prompt as VideoPrompt) : null
  );
  const [aiGeneratingImg, setAiGeneratingImg] = useState(false);
  const [aiGeneratingVid, setAiGeneratingVid] = useState(false);

  const promptSourceText = useMemo(
    () => getPromptSourceText(segment, mentionContext.contentMode, sourceDraft).trim(),
    [segment, mentionContext.contentMode, sourceDraft],
  );
  const referenceContext = useMemo(
    () => buildReferenceContext(segment, styleContext),
    [segment, styleContext],
  );

  const runPromptGeneration = async ({
    type,
    description,
    instruction,
    isEmpty,
    setGenerating,
    onGenerated,
    successMessage,
  }: {
    type: "image_prompt" | "video_prompt";
    description: string;
    instruction?: string;
    isEmpty: boolean;
    setGenerating: (value: boolean) => void;
    onGenerated: (prompt: string) => void;
    successMessage: string;
  }) => {
    if (isEmpty) {
      useAppStore.getState().pushToast("沒有可用的上下文或現有提示詞，無法生成提示詞！", "error");
      return;
    }

    setGenerating(true);
    try {
      const res = await API.generateAIDescription(projectName, {
        type,
        description,
        instruction,
        model: textModel || undefined,
      });
      onGenerated(res.prompt);
      useAppStore.getState().pushToast(successMessage, "success");
    } catch (err) {
      useAppStore.getState().pushToast(`AI 提示詞生成失敗: ${(err as Error).message}`, "error");
    } finally {
      setGenerating(false);
    }
  };

  const handleGeneratedImagePrompt = (newPrompt: string) => {
    if (isStructuredImage) {
      fireStructuredImage({ scene: newPrompt });
      return;
    }
    setImgText(newPrompt);
    fireString("image_prompt", "imagePrompt", newPrompt);
  };

  const handleGeneratedVideoPrompt = (newPrompt: string) => {
    if (isStructuredVideo) {
      fireStructuredVideo({ action: newPrompt });
      return;
    }
    setVidText(newPrompt);
    fireString("video_prompt", "videoPrompt", newPrompt);
  };

  const handleGenerateImagePromptAI = async () => {
    const sourceText = promptSourceText;
    const currentImgDesc = (isStructuredImage ? imgDraft?.scene : imgText) || "";

    await runPromptGeneration({
      type: "image_prompt",
      description: withReferenceContext(
        sourceText ? sourceText : `最佳化此提示詞: ${currentImgDesc}`,
        referenceContext,
      ),
      instruction: currentImgDesc ? `請基於當前提示詞進行細化 and 最佳化: ${currentImgDesc}` : undefined,
      isEmpty: !sourceText && !currentImgDesc.trim(),
      setGenerating: setAiGeneratingImg,
      onGenerated: handleGeneratedImagePrompt,
      successMessage: "分鏡圖提示詞生成成功",
    });
  };

  const handleGenerateVideoPromptAI = async () => {
    const sourceText = promptSourceText;
    const currentImgDesc = (isStructuredImage ? imgDraft?.scene : imgText) || "";
    const currentVidDesc = (isStructuredVideo ? vidDraft?.action : vidText) || "";

    const descriptionParts: string[] = [];
    if (currentImgDesc) descriptionParts.push(`分鏡預覽: ${currentImgDesc}`);
    if (sourceText) descriptionParts.push(`上下文內容:\n${sourceText}`);
    if (referenceContext) descriptionParts.push(referenceContext);

    await runPromptGeneration({
      type: "video_prompt",
      description: descriptionParts.join("\n") || `最佳化此影片動作提示詞: ${currentVidDesc}`,
      instruction: currentVidDesc ? `請基於當前動作提示詞進行細化 and 最佳化: ${currentVidDesc}` : undefined,
      isEmpty: !sourceText && !currentImgDesc && !currentVidDesc,
      setGenerating: setAiGeneratingVid,
      onGenerated: handleGeneratedVideoPrompt,
      successMessage: "影片提示詞生成成功",
    });
  };

  const isImagePromptEmpty = useMemo(() => {
    if (isStructuredImage) {
      return !image_prompt || !(image_prompt as ImagePrompt).scene?.trim();
    }
    return !imgText.trim();
  }, [isStructuredImage, image_prompt, imgText]);

  const isVideoPromptEmpty = useMemo(() => {
    if (isStructuredVideo) {
      return !video_prompt || !(video_prompt as VideoPrompt).action?.trim();
    }
    return !vidText.trim();
  }, [isStructuredVideo, video_prompt, vidText]);

  const prevSegmentIdRef = useRef(segmentId);

  useEffect(() => {
    if (prevSegmentIdRef.current === segmentId) {
      return;
    }

    prevSegmentIdRef.current = segmentId;
    setImgText(promptToStr(image_prompt, "scene"));
    setVidText(promptToStr(video_prompt, "action"));
    setImgDraft(isStructuredImage ? (image_prompt as ImagePrompt) : null);
    setVidDraft(isStructuredVideo ? (video_prompt as VideoPrompt) : null);
  }, [
    segmentId,
    image_prompt,
    video_prompt,
    isStructuredImage,
    isStructuredVideo,
  ]);

  useEffect(() => {
    if (!isStructuredImage) {
      setImgDraft(null);
      setImgText(promptToStr(image_prompt, "scene"));
    }
  }, [image_prompt, isStructuredImage]);

  useEffect(() => {
    if (!isStructuredVideo) {
      setVidDraft(null);
      setVidText(promptToStr(video_prompt, "action"));
    }
  }, [video_prompt, isStructuredVideo]);

  // ---- Firing helpers ----
  const fireStructuredImage = (patch: Partial<ImagePrompt>) => {
    setImgDraft((prev) => {
      const base = prev ?? (isStructuredImage ? image_prompt : null);
      if (!base) {
        return prev;
      }
      const merged = mergePromptPatch(
        base as unknown as Record<string, unknown>,
        patch as Record<string, unknown>
      ) as unknown as ImagePrompt;
      onMentionDraftChange("imagePrompt", merged);
      onUpdatePrompt?.(
        segmentId,
        "image_prompt",
        merged,
        buildPromptMentionUpdates("imagePrompt", merged),
      );
      return merged;
    });
  };

  const fireStructuredVideo = (patch: Partial<VideoPrompt>) => {
    setVidDraft((prev) => {
      const base = prev ?? (isStructuredVideo ? video_prompt : null);
      if (!base) {
        return prev;
      }
      const merged = mergePromptPatch(
        base as unknown as Record<string, unknown>,
        patch as Record<string, unknown>
      ) as unknown as VideoPrompt;
      onMentionDraftChange("videoPrompt", merged);
      onUpdatePrompt?.(
        segmentId,
        "video_prompt",
        merged,
        buildPromptMentionUpdates("videoPrompt", merged),
      );
      return merged;
    });
  };

  const fireString = (
    field: "image_prompt" | "video_prompt",
    key: PromptMentionDraftKey,
    value: string,
  ) => {
    onMentionDraftChange(key, value);
    onUpdatePrompt?.(segmentId, field, value, buildPromptMentionUpdates(key, value));
  };

  return (
    <div className="flex flex-col gap-3 p-3">
      <span className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-1">
        提示詞
      </span>

      {/* ---- Image Prompt ---- */}
      {(stage === undefined || stage === "storyboard") && (
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <ImageIcon className="h-3.5 w-3.5 text-gray-500" />
              <span className="text-[11px] font-semibold text-gray-400">
                Image Prompt
              </span>
            </div>
          </div>

          {isStructuredImage && imgDraft ? (
            <ImagePromptEditor
              prompt={imgDraft}
              onUpdate={fireStructuredImage}
              entities={mentionContext.entities}
              linkedNames={mentionContext.currentNames}
            />
          ) : (
            <AutoTextarea
              value={imgText}
              onChange={(v) => {
                setImgText(v);
                fireString("image_prompt", "imagePrompt", v);
              }}
              placeholder="分鏡圖描述..."
              entities={mentionContext.entities}
              linkedNames={mentionContext.currentNames}
              className="max-h-32 overflow-y-auto"
            />
          )}
          <PromptModelToolbar
            textModel={textModel}
            setTextModel={setTextModel}
            textModelOptions={textModelOptions}
            providerNames={providerNames}
            onGenerate={handleGenerateImagePromptAI}
            isGenerating={aiGeneratingImg}
            btnTitle="根據原文內容生成繪圖提示詞"
          />
          {isImagePromptEmpty && (
            <span className="text-[10px] text-red-400 font-medium">⚠️ 描述為空，請輸入分鏡圖描述以避免生成失敗</span>
          )}
        </div>
      )}

      {/* ---- Video Prompt ---- */}
      {(stage === undefined || stage === "video") && (
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <Film className="h-3.5 w-3.5 text-gray-500" />
              <span className="text-[11px] font-semibold text-gray-400">
                Video Prompt
              </span>
            </div>
          </div>

          {isStructuredVideo && vidDraft ? (
            <VideoPromptEditor
              prompt={vidDraft}
              onUpdate={fireStructuredVideo}
              speakerOptions={speakerOptions}
              entities={mentionContext.entities}
              linkedNames={mentionContext.currentNames}
            />
          ) : (
            <AutoTextarea
              value={vidText}
              onChange={(v) => {
                setVidText(v);
                fireString("video_prompt", "videoPrompt", v);
              }}
              placeholder="影片動作描述..."
              entities={mentionContext.entities}
              linkedNames={mentionContext.currentNames}
              className="max-h-32 overflow-y-auto"
            />
          )}
          <PromptModelToolbar
            textModel={textModel}
            setTextModel={setTextModel}
            textModelOptions={textModelOptions}
            providerNames={providerNames}
            onGenerate={handleGenerateVideoPromptAI}
            isGenerating={aiGeneratingVid}
            btnTitle="根據分鏡畫面與原文生成影片動作提示詞"
          />
          {isVideoPromptEmpty && (
            <span className="text-[10px] text-red-400 font-medium">⚠️ 描述為空，請輸入影片動作描述以避免生成失敗</span>
          )}
        </div>
      )}
    </div>
  );
}

interface PromptModelToolbarProps {
  textModel: string | null;
  setTextModel: (model: string | null) => void;
  textModelOptions?: string[];
  providerNames?: Record<string, string>;
  onGenerate: () => void;
  isGenerating: boolean;
  btnTitle: string;
}

function PromptModelToolbar({
  textModel,
  setTextModel,
  textModelOptions,
  providerNames,
  onGenerate,
  isGenerating,
  btnTitle,
}: PromptModelToolbarProps) {
  const globalDefaults = useGlobalModelDefaults();
  if (!textModelOptions || textModelOptions.length === 0) return null;

  return (
    <div className="mt-1.5 flex gap-2 w-full">
      <div className="w-[60%] min-w-0">
        <ProviderModelSelect
          value={textModel || ""}
          options={textModelOptions}
          providerNames={providerNames || {}}
          onChange={setTextModel}
          placeholder="選擇文字模型..."
          allowDefault={true}
          defaultLabel="專案預設模型"
          defaultModelValue={globalDefaults.text}
          className="w-full text-xs"
          size="sm"
        />
      </div>
      <button
        type="button"
        onClick={onGenerate}
        disabled={isGenerating}
        className="w-[40%] flex items-center justify-center gap-1.5 h-8 text-xs font-semibold text-white disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-none bg-indigo-600 hover:bg-indigo-500 rounded-lg transition-all truncate shadow-md shadow-indigo-500/5"
        title={btnTitle}
      >
        {isGenerating && <Loader2 className="h-3 w-3 animate-spin shrink-0" />}
        <span className="truncate">{isGenerating ? "生成中" : "生成提示詞"}</span>
      </button>
    </div>
  );
}
