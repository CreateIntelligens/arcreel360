import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ConfirmProvider } from "@/components/ui/ConfirmProvider";
import { TimelineCanvas } from "./TimelineCanvas";
import { API } from "@/api";
import { useCostStore } from "@/stores/cost-store";
import type { EpisodeCost, NarrationEpisodeScript, ProjectData } from "@/types";

vi.mock("@/api", () => ({
  API: {
    addEpisodeSegment: vi.fn(),
    addEpisodeScene: vi.fn(),
    getProject: vi.fn().mockResolvedValue({ project: {}, scripts: {}, asset_fingerprints: {} }),
    listFiles: vi.fn().mockResolvedValue({ files: { source: [] } }),
  },
}));

vi.mock("@/api/providers", () => ({
  providersApi: {
    getProviders: vi.fn().mockResolvedValue({ providers: [] }),
  },
}));

vi.mock("./SegmentCard", () => ({
  SegmentCard: () => <div data-testid="segment-card" />,
}));

vi.mock("./EpisodeActionsBar", () => ({
  EpisodeActionsBar: ({ activeTab }: { activeTab: string }) => (
    <div data-testid="episode-actions" data-active-tab={activeTab} />
  ),
}));

vi.mock("./SourceTextPanel", () => ({
  SourceTextPanel: () => <div data-testid="source-text-panel" />,
}));

vi.mock("./FinalVideoCard", () => ({
  FinalVideoCard: () => <div data-testid="final-video" />,
}));

vi.mock("./EpisodeSplitPanel", () => ({
  EpisodeSplitPanel: () => <div data-testid="episode-split-panel" />,
}));

vi.mock("./PreprocessingView", () => ({
  PreprocessingView: () => <div data-testid="preprocessing-view" />,
}));

function makeProjectData(): ProjectData {
  return {
    title: "Demo",
    content_mode: "narration",
    style: "Anime",
    episodes: [{ episode: 1, title: "第一集", script_file: "scripts/episode_1.json" }],
    characters: {},
    clues: {},
  };
}

function makeEmptyNarrationScript(
  overrides: Partial<NarrationEpisodeScript> = {},
): NarrationEpisodeScript {
  return {
    episode: 1,
    title: "第一集",
    content_mode: "narration",
    duration_seconds: 0,
    summary: "",
    novel: { title: "", chapter: "" },
    segments: [],
    ...overrides,
  };
}

function renderTimelineCanvas(ui: ReactElement) {
  return render(ui, { wrapper: ConfirmProvider });
}

function setEpisodeCost(cost: Partial<EpisodeCost> = {}) {
  const episodeCost: EpisodeCost = {
    episode: 1,
    title: "第一集",
    segments: [],
    totals: {
      estimate: {
        image: { USD: 0.12 },
        video: { USD: 0.34 },
      },
      actual: {
        image: { USD: 0.02 },
        video: { USD: 0.03 },
      },
    },
    ...cost,
  };
  useCostStore.setState({ _episodeIndex: new Map([[1, episodeCost]]) });
}

describe("TimelineCanvas", () => {
  beforeEach(() => {
    useCostStore.setState(useCostStore.getInitialState(), true);
    localStorage.clear();
    window.history.pushState(null, "", "/episodes/1");
  });

  it("defaults to preprocessing when opening an episode without a remembered timeline tab", () => {
    renderTimelineCanvas(
      <TimelineCanvas
        projectName="demo"
        episode={1}
        episodeTitle="第一集"
        hasDraft
        projectData={{
          ...makeProjectData(),
          status: {
            current_phase: "video",
            phase_progress: 80,
            characters: { total: 0, completed: 0 },
            clues: { total: 0, completed: 0 },
            scenes: { total: 0, completed: 0 },
            episodes_summary: {
              total: 1,
              scripted: 1,
              in_production: 0,
              completed: 0,
            },
          },
        }}
        episodeScript={makeEmptyNarrationScript()}
      />,
    );

    expect(screen.getByTestId("preprocessing-view")).toBeInTheDocument();
    expect(screen.getByTestId("episode-actions")).toHaveAttribute("data-active-tab", "preprocessing");
  });

  it("remembers the selected timeline tab for the next episode entry", () => {
    renderTimelineCanvas(
      <TimelineCanvas
        projectName="demo"
        episode={1}
        episodeTitle="第一集"
        hasDraft
        projectData={makeProjectData()}
        episodeScript={makeEmptyNarrationScript()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "影片時間線" }));

    expect(localStorage.getItem("arcreel:timeline_tab:demo")).toBe("video");
  });

  it("uses the remembered timeline tab when opening an episode without a tab query", () => {
    localStorage.setItem("arcreel:timeline_tab:demo", "video");

    renderTimelineCanvas(
      <TimelineCanvas
        projectName="demo"
        episode={1}
        episodeTitle="第一集"
        hasDraft
        projectData={makeProjectData()}
        episodeScript={makeEmptyNarrationScript()}
      />,
    );

    expect(screen.getByTestId("episode-actions")).toHaveAttribute("data-active-tab", "video");
  });

  it("opens the final video tab from the URL query", () => {
    window.history.pushState(null, "", "/episodes/1?tab=final");

    renderTimelineCanvas(
      <TimelineCanvas
        projectName="demo"
        episode={1}
        episodeTitle="第一集"
        hasDraft
        projectData={makeProjectData()}
        episodeScript={makeEmptyNarrationScript()}
      />,
    );

    expect(screen.getByTestId("episode-actions")).toHaveAttribute("data-active-tab", "final");
    expect(screen.getByTestId("final-video")).toBeInTheDocument();
  });

  it("keeps timeline tabs anchored below the episode title before variable actions", () => {
    renderTimelineCanvas(
      <TimelineCanvas
        projectName="demo"
        episode={1}
        episodeTitle="第一集"
        hasDraft
        projectData={makeProjectData()}
        episodeScript={makeEmptyNarrationScript()}
      />,
    );

    const titleButton = screen.getByRole("button", { name: "第一集" });
    const firstTab = screen.getByRole("button", { name: "預處理" });
    const actions = screen.getByTestId("episode-actions");

    expect(titleButton.compareDocumentPosition(firstTab) & Node.DOCUMENT_POSITION_FOLLOWING).not.toBe(0);
    expect(firstTab.compareDocumentPosition(actions) & Node.DOCUMENT_POSITION_FOLLOWING).not.toBe(0);
  });

  it("uses scenes when a script is drama-shaped even if the project is narration mode", () => {
    renderTimelineCanvas(
      <TimelineCanvas
        projectName="demo"
        episode={1}
        episodeTitle="第一集"
        projectData={makeProjectData()}
        episodeScript={{
          episode: 1,
          title: "第一集",
          duration_seconds: 8,
          summary: "",
          novel: { title: "", chapter: "" },
          scenes: [
            {
              scene_id: "scene_1",
              duration_seconds: 8,
              segment_break: false,
              scene_type: "dialogue",
              characters_in_scene: [],
              clues_in_scene: [],
              image_prompt: "image prompt",
              video_prompt: "video prompt",
              transition_to_next: "cut",
            },
          ],
        } as never}
      />,
    );

    expect(screen.getByText("1 個場景 · 約 8s")).toBeInTheDocument();
  });

  it("renders the editor with an add-segment button when the script has no segments", async () => {
    vi.mocked(API.addEpisodeSegment).mockResolvedValue({ segment: {}, segments_count: 1 });
    renderTimelineCanvas(
      <TimelineCanvas
        projectName="demo"
        episode={1}
        episodeTitle="第一集"
        projectData={makeProjectData()}
        episodeScript={makeEmptyNarrationScript()}
      />,
    );

    // 空狀態提示 + 新增按鈕
    expect(screen.getByText("這一集還沒有片段，點上方按鈕新增。")).toBeInTheDocument();
    const addBtn = screen.getByRole("button", { name: "新增片段" });
    expect(addBtn).not.toHaveClass("mb-4");
    fireEvent.click(addBtn);
    await waitFor(() => expect(API.addEpisodeSegment).toHaveBeenCalledWith("demo", 1));
    // 成功後會 refetch（getProject）
    await waitFor(() => expect(API.getProject).toHaveBeenCalledWith("demo"));
  });

  it("adds a segment to the route episode even when the script metadata is stale", async () => {
    vi.mocked(API.addEpisodeSegment).mockResolvedValue({ segment: {}, segments_count: 1 });
    renderTimelineCanvas(
      <TimelineCanvas
        projectName="demo"
        episode={2}
        episodeTitle="第二集"
        projectData={{
          ...makeProjectData(),
          episodes: [{ episode: 2, title: "第二集", script_file: "scripts/episode_2.json" }],
        }}
        episodeScript={makeEmptyNarrationScript({ title: "第二集" })}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "新增片段" }));

    await waitFor(() => expect(API.addEpisodeSegment).toHaveBeenCalledWith("demo", 2));
  });

  it("shows only storyboard costs in the storyboard tab summary", () => {
    setEpisodeCost();
    localStorage.setItem("arcreel:timeline_tab:demo", "storyboard");
    renderTimelineCanvas(
      <TimelineCanvas
        projectName="demo"
        episode={1}
        episodeTitle="第一集"
        projectData={makeProjectData()}
        episodeScript={makeEmptyNarrationScript()}
      />,
    );

    expect(screen.getAllByText("$0.12")).toHaveLength(2);
    expect(screen.getAllByText("$0.02")).toHaveLength(2);
    expect(screen.queryByText("$0.34")).not.toBeInTheDocument();
    expect(screen.queryByText("$0.03")).not.toBeInTheDocument();
  });
});
