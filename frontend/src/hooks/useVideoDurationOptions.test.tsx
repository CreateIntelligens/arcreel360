import { renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { API } from "@/api";
import { useVideoDurationOptions } from "./useVideoDurationOptions";
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
        capabilities: ["text_to_video", "image_to_video"],
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
        capabilities: ["text_to_video", "image_to_video"],
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

describe("useVideoDurationOptions", () => {
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

  it("uses only 8 seconds for 1080p Veo output", async () => {
    const { result } = renderHook(() =>
      useVideoDurationOptions("gemini-aistudio/veo-3.1-generate-preview", {
        currentResolution: "1080p",
      }),
    );

    await waitFor(() => expect(result.current).toEqual([8]));
  });

  it("uses only 8 seconds when a reference image is present", async () => {
    const { result } = renderHook(() =>
      useVideoDurationOptions("gemini-aistudio/veo-3.1-generate-preview", {
        currentResolution: "720p",
        hasReferenceImage: true,
      }),
    );

    await waitFor(() => expect(result.current).toEqual([8]));
  });

  it("keeps Lite 720p durations flexible and Lite 1080p locked to 8 seconds", async () => {
    const { result, rerender } = renderHook(
      ({ resolution }) =>
        useVideoDurationOptions("gemini-aistudio/veo-3.1-lite-generate-preview", {
          currentResolution: resolution,
        }),
      { initialProps: { resolution: "720p" } },
    );

    await waitFor(() => expect(result.current).toEqual([4, 6, 8]));

    rerender({ resolution: "1080p" });

    await waitFor(() => expect(result.current).toEqual([8]));
  });
});
