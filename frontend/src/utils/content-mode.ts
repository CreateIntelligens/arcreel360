export type ContentMode = "narration" | "drama";

interface ScriptContentModeCandidate {
  content_mode?: string;
  scenes?: unknown;
  segments?: unknown;
}

export function resolveEpisodeContentMode(
  script: unknown,
  fallbackMode?: string | null,
): ContentMode {
  const episodeScript = script as ScriptContentModeCandidate | null | undefined;

  if (Array.isArray(episodeScript?.scenes)) return "drama";
  if (Array.isArray(episodeScript?.segments)) return "narration";
  if (episodeScript?.content_mode === "drama") return "drama";
  if (episodeScript?.content_mode === "narration") return "narration";
  return fallbackMode === "drama" ? "drama" : "narration";
}
