import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Route, Router } from "wouter";
import { memoryLocation } from "wouter/memory-location";
import { API } from "@/api";
import { ProjectSettingsPage } from "@/components/pages/ProjectSettingsPage";
import { ConfirmProvider } from "@/components/ui/ConfirmProvider";
import { invalidateProviderModelsCache } from "@/utils/provider-models";
import type { GetSystemConfigResponse, ProjectData, ProviderInfo } from "@/types";

function makeConfigResponse(): GetSystemConfigResponse {
  return {
    settings: {
      assistant_provider: "claude",
      default_video_backend: "gemini/veo-3",
      default_image_backend: "gemini/imagen-4",
      default_text_backend: "",
      byteplus_video_endpoint_id: "",
      text_backend_script: "",
      text_backend_overview: "",
      text_backend_style: "",
      video_generate_audio: true,
      anthropic_api_key: { is_set: true, masked: "sk-ant-***" },
      anthropic_base_url: "",
      anthropic_model: "",
      anthropic_default_haiku_model: "",
      anthropic_default_opus_model: "",
      anthropic_default_sonnet_model: "",
      claude_code_subagent_model: "",
      agent_session_cleanup_delay_seconds: 300,
      agent_max_concurrent_sessions: 5,
    },
    options: {
      video_backends: ["gemini/veo-3"],
      image_backends: ["gemini/imagen-4"],
      text_backends: ["gemini/gemini-2.5-pro"],
      provider_names: { gemini: "Google Gemini" },
      assistant_providers: ["claude"],
    },
  };
}

const DEMO_PROJECT: ProjectData = {
  title: "Demo",
  content_mode: "narration",
  style: "Anime",
  episodes: [],
  characters: {},
  clues: {},
};

const PROVIDERS: ProviderInfo[] = [
  {
    id: "gemini",
    display_name: "Google Gemini",
    description: "Google Gemini API",
    status: "ready",
    media_types: ["image", "video", "text"],
    capabilities: [],
    configured_keys: ["api_key"],
    missing_keys: [],
    models: {
      "veo-3": {
        display_name: "Veo 3",
        media_type: "video",
        capabilities: [],
        default: true,
        supported_durations: [8],
        duration_resolution_constraints: {},
        supported_resolutions: ["720p", "1080p"],
        reference_image_force_duration: null,
        supported_image_sizes: [],
      },
      "imagen-4": {
        display_name: "Imagen 4",
        media_type: "image",
        capabilities: [],
        default: true,
        supported_durations: [],
        duration_resolution_constraints: {},
        supported_resolutions: [],
        reference_image_force_duration: null,
        supported_image_sizes: ["1K", "2K"],
      },
    },
  },
];

function renderPage() {
  const location = memoryLocation({ path: "/app/projects/demo/settings" });
  return render(
    <ConfirmProvider>
      <Router hook={location.hook}>
        <Route path="/app/projects/:projectName/settings" component={ProjectSettingsPage} />
      </Router>
    </ConfirmProvider>,
  );
}

describe("ProjectSettingsPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    invalidateProviderModelsCache();
    vi.spyOn(API, "getSystemConfig").mockResolvedValue(makeConfigResponse());
    vi.spyOn(API, "getProject").mockResolvedValue({
      project: DEMO_PROJECT,
      scripts: {},
      asset_fingerprints: {},
    });
    vi.spyOn(API, "getProviders").mockResolvedValue({ providers: PROVIDERS });
  });

  it("renders model dropdown popovers above the full-screen settings layer", async () => {
    renderPage();

    const [videoModelSelect] = await screen.findAllByRole("combobox");
    fireEvent.click(videoModelSelect);

    const listbox = await screen.findByRole("listbox", { name: "選擇模型" });
    expect(listbox.parentElement).toHaveClass("z-[55]");
  });
});
