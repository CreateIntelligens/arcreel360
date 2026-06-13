import { renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { API } from "@/api";
import { useVideoResolutionOptions } from "./useVideoResolutionOptions";
import type { ProviderInfo } from "@/types";

const providers: ProviderInfo[] = [
  {
    id: "gemini-aistudio",
    display_name: "AI Studio",
    description: "",
    status: "ready",
    media_types: ["video"],
    capabilities: ["text_to_video"],
    configured_keys: [],
    missing_keys: [],
    models: {
      "veo-3.1-generate-preview": {
        display_name: "Veo 3.1",
        media_type: "video",
        capabilities: ["text_to_video"],
        default: false,
        supported_durations: [4, 6, 8],
        duration_resolution_constraints: { "1080p": [8], "4k": [8] },
        supported_resolutions: ["720p", "1080p", "4k"],
        reference_image_force_duration: 8,
        supported_image_sizes: [],
      },
      "veo-3.1-lite-generate-preview": {
        display_name: "Veo 3.1 Lite",
        media_type: "video",
        capabilities: ["text_to_video"],
        default: true,
        supported_durations: [4, 6, 8],
        duration_resolution_constraints: { "1080p": [8] },
        supported_resolutions: ["720p", "1080p"],
        reference_image_force_duration: 8,
        supported_image_sizes: [],
      },
    },
  },
];

describe("useVideoResolutionOptions", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(API, "getProviders").mockResolvedValue({ providers });
    vi.spyOn(API, "listCustomProviders").mockResolvedValue({ providers: [] });
    vi.spyOn(API, "getSystemConfig").mockResolvedValue({
      settings: {
        default_video_backend: "gemini-aistudio/veo-3.1-generate-preview",
      },
      options: {},
    } as Awaited<ReturnType<typeof API.getSystemConfig>>);
  });

  it("returns Lite resolutions without 4k", async () => {
    const { result } = renderHook(() =>
      useVideoResolutionOptions("gemini-aistudio/veo-3.1-lite-generate-preview"),
    );

    await waitFor(() => expect(result.current).toEqual(["720p", "1080p"]));
  });
});
