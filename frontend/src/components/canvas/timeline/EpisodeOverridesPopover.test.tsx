import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { API } from "@/api";
import { providersApi } from "@/api/providers";
import { useAppStore } from "@/stores/app-store";
import { useProjectsStore } from "@/stores/projects-store";
import { EpisodeOverridesPopover } from "./EpisodeOverridesPopover";
import type { ProviderInfo } from "@/types";

vi.mock("@/api", () => ({
  API: {
    getProject: vi.fn().mockResolvedValue({
      project: {
        title: "Demo",
        content_mode: "narration",
        style: "Anime",
        episodes: [],
        characters: {},
        clues: {},
      },
      scripts: {},
      asset_fingerprints: {},
    }),
    updateEpisodeOverrides: vi.fn().mockResolvedValue({ success: true, overrides: {} }),
  },
}));

vi.mock("@/api/providers", () => ({
  providersApi: {
    getProviders: vi.fn(),
  },
}));

const PROVIDERS: ProviderInfo[] = [
  {
    id: "gemini",
    display_name: "Gemini",
    description: "",
    status: "ready",
    media_types: ["image", "video"],
    capabilities: [],
    configured_keys: [],
    missing_keys: [],
    models: {
      imagen: {
        display_name: "Imagen",
        media_type: "image",
        capabilities: [],
        default: true,
        supported_durations: [],
        duration_resolution_constraints: {},
        supported_resolutions: [],
        reference_image_force_duration: null,
        supported_image_sizes: ["1k"],
      },
      veo: {
        display_name: "Veo",
        media_type: "video",
        capabilities: [],
        default: true,
        supported_durations: [4, 8],
        duration_resolution_constraints: {},
        supported_resolutions: ["720p"],
        reference_image_force_duration: null,
        supported_image_sizes: [],
      },
    },
  },
];

describe("EpisodeOverridesPopover", () => {
  beforeEach(() => {
    useAppStore.setState(useAppStore.getInitialState(), true);
    useProjectsStore.setState(useProjectsStore.getInitialState(), true);
    vi.mocked(providersApi.getProviders).mockResolvedValue({ providers: PROVIDERS });
    vi.mocked(API.getProject).mockResolvedValue({
      project: {
        title: "Demo",
        content_mode: "narration",
        style: "Anime",
        episodes: [],
        characters: {},
        clues: {},
      },
      scripts: {},
      asset_fingerprints: {},
    });
    vi.mocked(API.updateEpisodeOverrides).mockResolvedValue({ success: true, overrides: {} });
  });

  it("shows only image override fields in storyboard mode", async () => {
    render(<EpisodeOverridesPopover projectName="demo" episode={1} mediaStage="storyboard" />);

    fireEvent.click(screen.getByRole("button", { name: "編輯第 1 集模型覆蓋設定" }));

    await waitFor(() => expect(providersApi.getProviders).toHaveBeenCalled());
    expect(screen.getByText(/圖片生成後端/)).toBeInTheDocument();
    expect(screen.getByText(/圖片尺寸/)).toBeInTheDocument();
    expect(screen.queryByText(/影片生成後端/)).not.toBeInTheDocument();
    expect(screen.queryByText(/影片解析度/)).not.toBeInTheDocument();
    expect(screen.queryByText(/影片時長/)).not.toBeInTheDocument();
  });

  it("saves only image override fields in storyboard mode", async () => {
    render(
      <EpisodeOverridesPopover
        projectName="demo"
        episode={1}
        mediaStage="storyboard"
        overrides={{
          image_backend: "gemini/imagen",
          image_size: "1k",
          video_backend: "gemini/veo",
          video_resolution: "720p",
          duration_seconds: 8,
        }}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "編輯第 1 集模型覆蓋設定" }));
    fireEvent.click(screen.getByRole("button", { name: "確認儲存" }));

    await waitFor(() =>
      expect(API.updateEpisodeOverrides).toHaveBeenCalledWith("demo", 1, {
        image_backend: "gemini/imagen",
        image_size: "1k",
      }),
    );
  });

  it("shows only video override fields in video mode", async () => {
    render(<EpisodeOverridesPopover projectName="demo" episode={1} mediaStage="video" />);

    fireEvent.click(screen.getByRole("button", { name: "編輯第 1 集模型覆蓋設定" }));

    await waitFor(() => expect(providersApi.getProviders).toHaveBeenCalled());
    expect(screen.getByText(/影片生成後端/)).toBeInTheDocument();
    expect(screen.getByText(/影片解析度/)).toBeInTheDocument();
    expect(screen.getByText(/影片時長/)).toBeInTheDocument();
    expect(screen.queryByText(/圖片生成後端/)).not.toBeInTheDocument();
    expect(screen.queryByText(/圖片尺寸/)).not.toBeInTheDocument();
  });
});
