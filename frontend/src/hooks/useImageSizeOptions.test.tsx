import { renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { API } from "@/api";
import { useImageSizeOptions } from "./useImageSizeOptions";
import { invalidateProviderModelsCache } from "@/utils/provider-models";
import type { ProviderInfo } from "@/types";

const providers: ProviderInfo[] = [
  {
    id: "gemini-aistudio",
    display_name: "AI Studio",
    description: "",
    status: "ready",
    media_types: ["image", "video"],
    capabilities: ["text_to_image"],
    configured_keys: [],
    missing_keys: [],
    models: {
      "flash-image": {
        display_name: "Flash Image",
        media_type: "image",
        capabilities: ["text_to_image"],
        default: true,
        supported_durations: [],
        duration_resolution_constraints: {},
        supported_resolutions: [],
        reference_image_force_duration: null,
        supported_image_sizes: ["480p", "720p", "1K"],
      },
      "no-sizes-image": {
        display_name: "No Sizes Image",
        media_type: "image",
        capabilities: ["text_to_image"],
        default: false,
        supported_durations: [],
        duration_resolution_constraints: {},
        supported_resolutions: [],
        reference_image_force_duration: null,
        supported_image_sizes: [],
      },
      "veo-3.1": {
        display_name: "Veo",
        media_type: "video",
        capabilities: ["text_to_video"],
        default: false,
        supported_durations: [4, 6, 8],
        duration_resolution_constraints: {},
        supported_resolutions: ["720p"],
        reference_image_force_duration: null,
        supported_image_sizes: [],
      },
    },
  },
];

describe("useImageSizeOptions", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    invalidateProviderModelsCache();
    vi.spyOn(API, "getProviders").mockResolvedValue({ providers });
    vi.spyOn(API, "listCustomProviders").mockResolvedValue({ providers: [] });
    vi.spyOn(API, "getSystemConfig").mockResolvedValue({
      settings: { default_image_backend: "gemini-aistudio/flash-image" },
      options: {},
    } as Awaited<ReturnType<typeof API.getSystemConfig>>);
  });

  it("returns declared sizes for a model that has them", async () => {
    const { result } = renderHook(() =>
      useImageSizeOptions("gemini-aistudio/flash-image"),
    );
    await waitFor(() => expect(result.current).toEqual(["480p", "720p", "1K"]));
  });

  it("returns undefined when the model declares no sizes", async () => {
    const { result } = renderHook(() =>
      useImageSizeOptions("gemini-aistudio/no-sizes-image"),
    );
    // wait for providers to load, then assert undefined (caller falls back)
    await waitFor(() => expect(API.getProviders).toHaveBeenCalled());
    expect(result.current).toBeUndefined();
  });

  it("returns undefined for an unknown model", async () => {
    const { result } = renderHook(() =>
      useImageSizeOptions("gemini-aistudio/does-not-exist"),
    );
    await waitFor(() => expect(API.getProviders).toHaveBeenCalled());
    expect(result.current).toBeUndefined();
  });
});
