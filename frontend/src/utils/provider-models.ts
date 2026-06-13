import { API } from "@/api";
import type { CustomProviderInfo, ModelInfoResponse, ProviderInfo } from "@/types";

export const DEFAULT_DURATIONS: readonly number[] = [4, 6, 8];
export const DEFAULT_RESOLUTIONS: readonly string[] = ["720p", "1080p", "4k"];
export const DEFAULT_IMAGE_SIZES: readonly string[] = ["1K"];

export interface MediaModelOptions {
  image: string[];
  video: string[];
  text: string[];
  providerNames: Record<string, string>;
}

export const EMPTY_MEDIA_MODEL_OPTIONS: MediaModelOptions = {
  image: [],
  video: [],
  text: [],
  providerNames: {},
};

export function shouldHideTextModelOption(value: string): boolean {
  const lower = value.toLowerCase();
  return lower.startsWith("byteplus/doubao-seed") || lower.startsWith("ark/doubao-seed");
}

const CUSTOM_PREFIX = "custom-";
const LEGACY_PROVIDER_IDS: Record<string, string> = {
  ark: "byteplus",
  seedance: "byteplus",
};
const DEFAULT_VIDEO_RESOLUTION_BY_PROVIDER: Record<string, string> = {
  gemini: "1080p",
  "gemini-aistudio": "1080p",
  "gemini-vertex": "1080p",
  byteplus: "720p",
  ark: "720p",
  seedance: "720p",
  grok: "720p",
  openai: "720p",
};

// ---------------------------------------------------------------------------
// Built-in providers cache
// ---------------------------------------------------------------------------

let _cache: ProviderInfo[] | null = null;
let _promise: Promise<ProviderInfo[]> | null = null;

/** Fetch (or return cached) built-in provider list including models. */
export async function getProviderModels(): Promise<ProviderInfo[]> {
  if (_cache) return _cache;
  if (!_promise) {
    _promise = API.getProviders()
      .then((res) => {
        _cache = res.providers;
        _promise = null;
        return _cache;
      })
      .catch((err) => {
        _promise = null;
        throw err;
      });
  }
  return _promise;
}

// ---------------------------------------------------------------------------
// Custom providers cache
// ---------------------------------------------------------------------------

let _customCache: CustomProviderInfo[] | null = null;
let _customPromise: Promise<CustomProviderInfo[]> | null = null;

/** Fetch (or return cached) custom provider list. */
export async function getCustomProviderModels(): Promise<CustomProviderInfo[]> {
  if (_customCache) return _customCache;
  if (!_customPromise) {
    _customPromise = API.listCustomProviders()
      .then((res) => {
        _customCache = res.providers;
        _customPromise = null;
        return _customCache;
      })
      .catch((err) => {
        _customPromise = null;
        throw err;
      });
  }
  return _customPromise;
}

// ---------------------------------------------------------------------------
// Cache invalidation
// ---------------------------------------------------------------------------

/** Invalidate all provider caches (call after provider config changes). */
export function invalidateProviderModelsCache(): void {
  _cache = null;
  _promise = null;
  _customCache = null;
  _customPromise = null;
}

export function buildMediaModelOptions(providers: ProviderInfo[] | null | undefined): MediaModelOptions {
  if (!providers) return EMPTY_MEDIA_MODEL_OPTIONS;

  const image: string[] = [];
  const video: string[] = [];
  const text: string[] = [];
  const providerNames: Record<string, string> = {};

  for (const provider of providers) {
    if (provider.status !== "ready") continue;

    providerNames[provider.id] = provider.display_name;
    for (const [modelId, info] of Object.entries(provider.models ?? {})) {
      const value = `${provider.id}/${modelId}`;
      if (info.media_type === "image") {
        image.push(value);
      } else if (info.media_type === "video") {
        video.push(value);
      } else if (info.media_type === "text" && !shouldHideTextModelOption(value)) {
        text.push(value);
      }
    }
  }

  return { image, video, text, providerNames };
}

// ---------------------------------------------------------------------------
// Lookup
// ---------------------------------------------------------------------------

/**
 * Given a video backend string like "gemini-aistudio/veo-3.1-generate-preview"
 * or "custom-3/my-model", look up supported_durations.
 * Returns undefined if provider/model not found.
 */
export function lookupSupportedDurations(
  providers: ProviderInfo[],
  videoBackend: string,
  customProviders?: CustomProviderInfo[],
): number[] | undefined {
  const parsed = parseVideoBackend(videoBackend);
  if (!parsed) return undefined;
  const { providerId, modelId } = parsed;

  // Custom provider: "custom-{db_id}/{model_id}"
  if (providerId.startsWith(CUSTOM_PREFIX) && customProviders) {
    const dbId = parseInt(providerId.slice(CUSTOM_PREFIX.length), 10);
    const cp = customProviders.find((p) => p.id === dbId);
    const model = cp?.models?.find((m) => m.model_id === modelId);
    if (model?.supported_durations?.length) {
      return model.supported_durations;
    }
    return undefined;
  }

  // Built-in provider
  const provider = providers.find((p) => p.id === providerId);
  const model = provider?.models?.[modelId];
  return model?.supported_durations?.length
    ? model.supported_durations
    : undefined;
}

export function lookupVideoModelInfo(
  providers: ProviderInfo[],
  videoBackend: string,
): ModelInfoResponse | undefined {
  const parsed = parseVideoBackend(videoBackend);
  if (!parsed || parsed.providerId.startsWith(CUSTOM_PREFIX)) return undefined;

  const provider = providers.find((p) => p.id === parsed.providerId);
  return provider?.models?.[parsed.modelId];
}

export function lookupSupportedResolutions(
  providers: ProviderInfo[],
  videoBackend: string,
): string[] | undefined {
  const model = lookupVideoModelInfo(providers, videoBackend);
  return model?.supported_resolutions?.length ? model.supported_resolutions : undefined;
}

export function lookupDefaultResolution(videoBackend: string): string | undefined {
  const parsed = parseVideoBackend(videoBackend);
  if (!parsed) return undefined;
  return DEFAULT_VIDEO_RESOLUTION_BY_PROVIDER[parsed.providerId];
}

/**
 * Given an image backend string like "gemini-aistudio/gemini-3.1-flash-image-preview",
 * look up the model's supported_image_sizes. Returns undefined if not found or
 * the model declares none (caller falls back to DEFAULT_IMAGE_SIZES).
 * Custom providers have no image-size declaration yet, so they return undefined.
 */
export function lookupSupportedImageSizes(
  providers: ProviderInfo[],
  imageBackend: string,
): string[] | undefined {
  const parsed = parseVideoBackend(imageBackend);
  if (!parsed || parsed.providerId.startsWith(CUSTOM_PREFIX)) return undefined;

  const provider = providers.find((p) => p.id === parsed.providerId);
  const model = provider?.models?.[parsed.modelId];
  return model?.supported_image_sizes?.length ? model.supported_image_sizes : undefined;
}

export function resolveVideoDurationOptions(
  model: ModelInfoResponse | undefined,
  fallbackDurations: number[] | undefined,
  options: {
    currentResolution?: string | null;
    hasReferenceImage?: boolean;
  } = {},
): number[] | undefined {
  if (!model) {
    return fallbackDurations;
  }

  if (options.hasReferenceImage && model.reference_image_force_duration) {
    return [model.reference_image_force_duration];
  }

  const resolution = options.currentResolution;
  if (resolution && model.duration_resolution_constraints?.[resolution]?.length) {
    return model.duration_resolution_constraints[resolution];
  }

  return model.supported_durations?.length
    ? model.supported_durations
    : fallbackDurations;
}

export function getDurationConstraintReason(
  options: {
    currentResolution?: string | null;
    hasReferenceImage?: boolean;
  },
): string | undefined {
  if (options.hasReferenceImage) return "參考圖強制 8 秒";
  if (options.currentResolution === "1080p") return "1080p 限制";
  if (options.currentResolution === "4k") return "4k 限制";
  return undefined;
}

export function coerceDurationToOptions(duration: number, options: readonly number[]): number {
  const valid = [...options].sort((a, b) => a - b);
  if (valid.length === 0) return duration;
  for (let i = valid.length - 1; i >= 0; i -= 1) {
    if (valid[i] <= duration) return valid[i];
  }
  return valid[0];
}

function parseVideoBackend(videoBackend: string): { providerId: string; modelId: string } | null {
  const slashIdx = videoBackend.indexOf("/");
  if (slashIdx === -1) return null;
  const providerId = videoBackend.slice(0, slashIdx);
  return {
    providerId: LEGACY_PROVIDER_IDS[providerId] ?? providerId,
    modelId: videoBackend.slice(slashIdx + 1),
  };
}
