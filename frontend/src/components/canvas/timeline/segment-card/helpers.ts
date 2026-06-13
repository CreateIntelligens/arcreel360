import {
  extractEntityMentionsFromValue,
  type EntityMentionNames,
  type EntityMentionSources,
} from "@/utils/entity-mentions";
import type {
  NarrationSegment,
  DramaScene,
  ImagePrompt,
  VideoPrompt,
} from "@/types";
import type {
  Segment,
  SegmentMentionDrafts,
  SegmentUpdateExtras,
} from "./types";

export interface SegmentMentionContext {
  contentMode: "narration" | "drama";
  currentNames: EntityMentionNames;
  entities: EntityMentionSources;
}

export const MENTION_UPDATE_FIELDS = {
  narration: {
    characters: "characters_in_segment",
    clues: "clues_in_segment",
    scene: "scene_in_segment",
  },
  drama: {
    characters: "characters_in_scene",
    clues: "clues_in_scene",
    scene: "scene_in_scene",
  },
} as const;

export const EMPTY_NAMES: readonly string[] = Object.freeze([]);

export function getSegmentId(segment: Segment, mode: "narration" | "drama"): string {
  return mode === "narration"
    ? (segment as NarrationSegment).segment_id
    : (segment as DramaScene).scene_id;
}

export function getSegmentField(
  segment: Segment,
  mode: "narration" | "drama",
  narrationKey: keyof NarrationSegment,
  dramaKey: keyof DramaScene,
): string[] {
  return mode === "narration"
    ? (((segment as NarrationSegment)[narrationKey] as string[] | undefined) ?? (EMPTY_NAMES as string[]))
    : (((segment as DramaScene)[dramaKey] as string[] | undefined) ?? (EMPTY_NAMES as string[]));
}

export function getCharacterNames(segment: Segment, mode: "narration" | "drama"): string[] {
  return getSegmentField(segment, mode, "characters_in_segment", "characters_in_scene");
}

export function getClueNames(segment: Segment, mode: "narration" | "drama"): string[] {
  return getSegmentField(segment, mode, "clues_in_segment", "clues_in_scene");
}

export function getSceneName(segment: Segment, mode: "narration" | "drama"): string | null {
  return mode === "narration"
    ? ((segment as NarrationSegment).scene_in_segment ?? null)
    : ((segment as DramaScene).scene_in_scene ?? null);
}

export function getSourceMentionValue(segment: Segment, mode: "narration" | "drama"): string {
  return mode === "narration"
    ? ((segment as NarrationSegment).novel_text ?? "")
    : ((segment as DramaScene).scene_description ?? "");
}

export function getSegmentMentionDrafts(
  segment: Segment,
  mode: "narration" | "drama",
): SegmentMentionDrafts {
  return {
    source: getSourceMentionValue(segment, mode),
    imagePrompt: segment.image_prompt ?? "",
    videoPrompt: segment.video_prompt ?? "",
  };
}

export function getMentionDraftValues(drafts: SegmentMentionDrafts): unknown[] {
  return [drafts.source, drafts.imagePrompt, drafts.videoPrompt];
}

export function sameNames(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false;
  const bSet = new Set(b);
  return a.every((name) => bSet.has(name));
}

export function sameMentionNames(a: EntityMentionNames, b: EntityMentionNames): boolean {
  return (
    sameNames(a.characterNames, b.characterNames) &&
    sameNames(a.clueNames, b.clueNames) &&
    a.sceneName === b.sceneName
  );
}

export function buildMentionFieldUpdates(
  value: unknown,
  mentionContext: SegmentMentionContext,
): SegmentUpdateExtras | undefined {
  const { contentMode, currentNames, entities } = mentionContext;
  const mentions = extractEntityMentionsFromValue(value, entities);
  if (sameMentionNames(mentions, currentNames)) {
    return undefined;
  }

  const fields = MENTION_UPDATE_FIELDS[contentMode];
  const updates: SegmentUpdateExtras = {};

  if (
    !sameNames(mentions.characterNames, currentNames.characterNames) ||
    !sameNames(mentions.clueNames, currentNames.clueNames)
  ) {
    updates[fields.characters] = mentions.characterNames;
    updates[fields.clues] = mentions.clueNames;
  }

  if (mentions.sceneName !== currentNames.sceneName) {
    updates[fields.scene] = mentions.sceneName;
  }

  return Object.keys(updates).length > 0 ? updates : undefined;
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export function isStructuredImagePromptValue(value: unknown): value is ImagePrompt {
  if (!isRecord(value) || typeof value.scene !== "string") {
    return false;
  }

  const composition = value.composition;
  if (!isRecord(composition)) {
    return false;
  }

  return (
    typeof composition.shot_type === "string" &&
    typeof composition.lighting === "string" &&
    typeof composition.ambiance === "string"
  );
}

export function isStructuredVideoPromptValue(value: unknown): value is VideoPrompt {
  if (
    !isRecord(value) ||
    typeof value.action !== "string" ||
    typeof value.camera_motion !== "string" ||
    typeof value.ambiance_audio !== "string"
  ) {
    return false;
  }

  const dialogue = value.dialogue;
  if (dialogue === undefined) {
    return true;
  }
  if (!Array.isArray(dialogue)) {
    return false;
  }

  return dialogue.every(
    (item) =>
      isRecord(item) &&
      typeof item.speaker === "string" &&
      typeof item.line === "string"
  );
}

export function mergePromptPatch<T extends Record<string, unknown>>(
  base: T,
  patch: Record<string, unknown>
): T {
  const merged: Record<string, unknown> = { ...base };

  for (const [k, v] of Object.entries(patch)) {
    if (
      isRecord(v) &&
      isRecord(base[k]) &&
      !Array.isArray(v) &&
      !Array.isArray(base[k])
    ) {
      merged[k] = { ...(base[k] as Record<string, unknown>), ...v };
    } else {
      merged[k] = v;
    }
  }

  return merged as T;
}
