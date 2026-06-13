import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Router, useLocation } from "wouter";
import { memoryLocation } from "wouter/memory-location";
import { API } from "@/api";
import { ConfirmProvider } from "@/components/ui/ConfirmProvider";
import { AssetSidebar } from "@/components/layout/AssetSidebar";
import { useAppStore } from "@/stores/app-store";
import { useProjectsStore } from "@/stores/projects-store";
import type { ProjectData } from "@/types";

function makeProjectData(overrides: Partial<ProjectData> = {}): ProjectData {
  return {
    title: "Demo",
    content_mode: "narration",
    style: "Anime",
    episodes: [{ episode: 1, title: "第一集", script_file: "scripts/episode_1.json" }],
    characters: {},
    clues: {},
    ...overrides,
  };
}

function LocationProbe() {
  const [location] = useLocation();
  return <div data-testid="location">{location}</div>;
}

function renderSidebar(path = "/") {
  const { hook } = memoryLocation({ path });
  return render(
    <ConfirmProvider>
      <Router hook={hook}>
        <LocationProbe />
        <AssetSidebar />
      </Router>
    </ConfirmProvider>,
  );
}

describe("AssetSidebar", () => {
  beforeEach(() => {
    useProjectsStore.setState(useProjectsStore.getInitialState(), true);
    useAppStore.setState(useAppStore.getInitialState(), true);
    vi.restoreAllMocks();
    vi.spyOn(API, "listFiles").mockResolvedValue({ files: { source: [] } });
  });

  it("creates the next episode from the scripts section action", async () => {
    const project = makeProjectData();
    const updatedProject = makeProjectData({
      episodes: [
        ...project.episodes,
        { episode: 2, title: "第 2 集", script_file: "scripts/episode_2.json" },
      ],
    });
    useProjectsStore.setState({
      currentProjectName: "demo",
      currentProjectData: project,
      currentScripts: { "episode_1.json": {} as never },
    });
    vi.spyOn(API, "createEpisode").mockResolvedValue({
      success: true,
      episode: { episode: 2, title: "第 2 集", script_file: "scripts/episode_2.json" },
      project: updatedProject,
    });

    renderSidebar();

    fireEvent.click(screen.getByTitle("新增劇本"));

    await waitFor(() => {
      expect(API.createEpisode).toHaveBeenCalledWith("demo", { episode: 2 });
    });
    expect(screen.getByTestId("location")).toHaveTextContent("/episodes/2");
    expect(useProjectsStore.getState().currentProjectData?.episodes).toHaveLength(2);
    expect(useProjectsStore.getState().currentScripts).toHaveProperty("episode_1.json");
    expect(useAppStore.getState().toast?.text).toContain("E2 已新增");
  });
});
