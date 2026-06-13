import type {
  NarrationSegment,
  DramaScene,
  Character,
  Clue,
  Scene,
} from "@/types";

export type Segment = NarrationSegment | DramaScene;
export type SegmentUpdateExtras = Record<string, unknown>;

export interface SegmentMentionDrafts {
  source: unknown;
  imagePrompt: unknown;
  videoPrompt: unknown;
}

export type SegmentMentionDraftKey = keyof SegmentMentionDrafts;
export type PromptMentionDraftKey = Exclude<SegmentMentionDraftKey, "source">;

export type SegmentUpdateHandler = (
  segmentId: string,
  field: string,
  value: unknown,
  extraUpdates?: SegmentUpdateExtras,
) => void;

export interface SegmentStyleContext {
  style?: string | null;
  styleDescription?: string | null;
  styleImage?: string | null;
}

export interface SegmentCardProps {
  segment: Segment;
  contentMode: "narration" | "drama";
  aspectRatio: string;
  characters: Record<string, Character>;
  clues: Record<string, Clue>;
  scenes?: Record<string, Scene>;
  projectName: string;
  episode?: number;
  scriptFile?: string;
  videoBackend?: string | null;
  currentResolution?: string | null;
  durationOptions?: number[];
  durationConstraintReason?: string;
  onUpdatePrompt?: SegmentUpdateHandler;
  onGenerateStoryboard?: (segmentId: string) => void;
  onGenerateVideo?: (segmentId: string) => void;
  onRestoreStoryboard?: () => Promise<void> | void;
  onRestoreVideo?: () => Promise<void> | void;
  onDelete?: () => void;
  generatingStoryboard?: boolean;
  generatingVideo?: boolean;
  onUploadReference?: (segmentId: string, file: File) => Promise<void> | void;
  onRemoveReference?: (segmentId: string) => Promise<void> | void;
  stage?: "storyboard" | "video";
  imageModelOptions?: string[];
  videoModelOptions?: string[];
  textModelOptions?: string[];
  providerNames?: Record<string, string>;
  styleContext?: SegmentStyleContext;
  onUpdateSceneBackend?: (
    segmentId: string,
    patch: { image_backend?: string | null; video_backend?: string | null }
  ) => Promise<void> | void;
}
