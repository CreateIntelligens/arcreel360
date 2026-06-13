import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Router } from "wouter";
import { memoryLocation } from "wouter/memory-location";
import { API } from "@/api";
import { useConfigStatusStore } from "@/stores/config-status-store";
import { SystemConfigPage } from "@/components/pages/SystemConfigPage";
import type { GetSystemConfigResponse, ProviderInfo } from "@/types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeConfigResponse(
  overrides?: Partial<GetSystemConfigResponse["settings"]>,
): GetSystemConfigResponse {
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
      ...overrides,
    },
    options: {
      video_backends: ["gemini/veo-3"],
      image_backends: ["gemini/imagen-4"],
      text_backends: [],
      assistant_providers: ["claude", "gemini-lite", "gemini-full", "openai-lite", "openai-full"],
    },
  };
}

function makeProviders(overrides?: Partial<ProviderInfo>): { providers: ProviderInfo[] } {
  return {
    providers: [
      {
        id: "gemini",
        display_name: "Google Gemini",
        description: "Google Gemini API",
        status: "ready",
        media_types: ["image", "video", "text"],
        capabilities: [],
        configured_keys: ["api_key"],
        missing_keys: [],
        models: {},
        ...overrides,
      },
    ],
  };
}

function renderPage(path = "/app/settings") {
  const location = memoryLocation({ path, record: true });
  return render(
    <Router hook={location.hook}>
      <SystemConfigPage />
    </Router>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("SystemConfigPage", () => {
  beforeEach(() => {
    useConfigStatusStore.setState(useConfigStatusStore.getInitialState(), true);
    vi.restoreAllMocks();

    // Default: silence child section network calls so tests don't hang
    vi.spyOn(API, "getSystemConfig").mockResolvedValue(makeConfigResponse());
    vi.spyOn(API, "getProviders").mockResolvedValue(makeProviders());
    vi.spyOn(API, "listCustomProviders").mockResolvedValue({ providers: [] });
    vi.spyOn(API, "getProviderConfig").mockResolvedValue({
      id: "gemini",
      display_name: "Google Gemini",
      status: "ready",
      media_types: ["image", "video"],
      capabilities: [],
      fields: [],
    } as never);
    vi.spyOn(API, "listCredentials").mockResolvedValue({ credentials: [] });
    vi.spyOn(API, "getUsageStatsGrouped").mockResolvedValue({ stats: [], period: { start: "", end: "" } });
  });

  it("renders the page header", () => {
    renderPage();
    expect(screen.getByText("設定")).toBeInTheDocument();
    expect(screen.getByText("系統設定與 API 存取管理")).toBeInTheDocument();
  });

  it("renders all 5 sidebar sections", () => {
    renderPage();
    expect(screen.getByRole("button", { name: /AI Agent/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /供應商/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /模型選擇/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /用量統計/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /API 管理/ })).toBeInTheDocument();
  });

  it("defaults to the AI Agent section", () => {
    renderPage();
    const agentButton = screen.getByRole("button", { name: /AI Agent/ });
    expect(agentButton.className).toContain("workbench-panel-strong");
  });

  it("keeps assistant runtime provider columns visually aligned", async () => {
    renderPage();

    expect(await screen.findByText("執行時供應商與模式")).toBeInTheDocument();

    const grid = screen.getByTestId("assistant-runtime-grid");
    expect(grid).toHaveClass("grid");
    expect(grid.className).toContain("grid-cols-[8rem_repeat(3,minmax(7.5rem,1fr))]");
    for (const provider of ["Gemini", "OpenAI", "Claude"]) {
      expect(screen.getByText(provider)).toHaveClass("justify-center");
    }
  });

  it("allows selecting OpenAI workflow mode", async () => {
    renderPage();

    const openaiWorkflow = await screen.findByRole("button", { name: "OpenAI 工作流模式 選擇" });
    expect(openaiWorkflow).toBeEnabled();

    fireEvent.click(openaiWorkflow);

    expect(await screen.findByText("OpenAI · 工作流模式")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "OpenAI 工作流模式 使用中" })).toHaveTextContent("✓ 使用中");
  });

  it("clicking 供應商 makes it the active section", async () => {
    renderPage();
    const providersButton = screen.getByRole("button", { name: /供應商/ });
    fireEvent.click(providersButton);
    await waitFor(() => {
      expect(providersButton.className).toContain("workbench-panel-strong");
    });
  });

  it("clicking 模型選擇 makes it the active section", async () => {
    renderPage();
    const mediaButton = screen.getByRole("button", { name: /模型選擇/ });
    fireEvent.click(mediaButton);
    await waitFor(() => {
      expect(mediaButton.className).toContain("workbench-panel-strong");
    });
  });

  it("saves BytePlus video endpoint id from the model section", async () => {
    const updateSpy = vi
      .spyOn(API, "updateSystemConfig")
      .mockResolvedValue(makeConfigResponse({ byteplus_video_endpoint_id: "ep-20260508120826-lkcjf" }));

    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /模型選擇/ }));

    const endpointInput = await screen.findByLabelText("BytePlus ModelArk Endpoint ID");
    fireEvent.change(endpointInput, { target: { value: "ep-20260508120826-lkcjf" } });
    fireEvent.click(screen.getByRole("button", { name: "儲存" }));

    await waitFor(() => {
      expect(updateSpy).toHaveBeenCalledWith({
        byteplus_video_endpoint_id: "ep-20260508120826-lkcjf",
      });
    });
  });

  it("clicking 用量統計 makes it the active section", async () => {
    renderPage();
    const usageButton = screen.getByRole("button", { name: /用量統計/ });
    fireEvent.click(usageButton);
    await waitFor(() => {
      expect(usageButton.className).toContain("workbench-panel-strong");
    });
  });

  it("shows config warning banner when there are provider issues", async () => {
    vi.spyOn(API, "getSystemConfig").mockResolvedValue(
      makeConfigResponse({ assistant_provider: "gemini-lite", anthropic_api_key: { is_set: false, masked: null } }),
    );
    vi.spyOn(API, "getProviders").mockResolvedValue(makeProviders({ id: "openai", status: "ready", media_types: ["image", "video", "text"] }));

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("以下必填設定尚未完成：")).toBeInTheDocument();
    });
    expect(
      screen.getByRole("button", { name: /Gemini AI Agent 未設定可用的 Gemini 文字供應商/ }),
    ).toBeInTheDocument();
  });

  it("does not show warning banner when config is complete", async () => {
    renderPage();

    // Give time for config status to load
    await waitFor(() => {
      expect(API.getProviders).toHaveBeenCalled();
    });

    expect(screen.queryByText("以下必填設定尚未完成：")).not.toBeInTheDocument();
  });

  it("renders the back link that navigates to projects", () => {
    renderPage();
    const link = screen.getByRole("link", { name: "返回專案大廳" });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute("href", "/app/projects");
  });
});
