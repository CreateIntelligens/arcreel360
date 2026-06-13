import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { API } from "@/api";
import { ConfirmProvider } from "@/components/ui/ConfirmProvider";
import { useAppStore } from "@/stores/app-store";
import { useProjectsStore } from "@/stores/projects-store";
import { EpisodeActionsBar } from "./EpisodeActionsBar";

vi.mock("@/api", () => ({
  API: {
    batchGenerateStoryboards: vi.fn(),
    generateEpisodeScript: vi.fn(),
  },
}));

function renderActions(ui: ReactElement) {
  return render(ui, { wrapper: ConfirmProvider });
}

function renderTimelineActions() {
  return renderActions(
    <EpisodeActionsBar
      projectName="demo"
      episode={1}
      scriptFile="scripts/episode_1.json"
      hasScript
    />,
  );
}

describe("EpisodeActionsBar", () => {
  beforeEach(() => {
    useAppStore.setState(useAppStore.getInitialState(), true);
    useProjectsStore.setState(useProjectsStore.getInitialState(), true);
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(API.batchGenerateStoryboards).mockResolvedValue({ enqueued: ["SEG-1"], skipped: [] });
    vi.mocked(API.generateEpisodeScript).mockResolvedValue({
      script_file: "scripts/episode_1.json",
      segments_count: 3,
    });
  });

  it("opens storyboard generation choices from the batch button", async () => {
    renderTimelineActions();

    expect(screen.queryByRole("button", { name: "強制重生" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "批次生圖" }));

    expect(await screen.findByRole("dialog", { name: "批次生圖" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "只生成缺少的分鏡" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "全部重生分鏡" })).toBeInTheDocument();
    expect(API.batchGenerateStoryboards).not.toHaveBeenCalled();
  });

  it("can force regenerate all storyboards from the choice dialog", async () => {
    renderTimelineActions();

    fireEvent.click(screen.getByRole("button", { name: "批次生圖" }));
    fireEvent.click(await screen.findByRole("button", { name: "全部重生分鏡" }));

    await waitFor(() => {
      expect(API.batchGenerateStoryboards).toHaveBeenCalledWith("demo", {
        script_file: "scripts/episode_1.json",
        force: true,
      });
    });
  });

  it("does not render the batch video generation action", () => {
    renderTimelineActions();

    expect(screen.queryByRole("button", { name: "批次生成影片" })).not.toBeInTheDocument();
  });

  it("renders storyboard generation on storyboard tab, no compose outside final tab", () => {
    // 1. Storyboard tab (預設)
    const { unmount } = renderActions(
      <EpisodeActionsBar
        projectName="demo"
        episode={1}
        scriptFile="scripts/episode_1.json"
        hasScript
        activeTab="storyboard"
      />
    );
    expect(screen.getByRole("button", { name: "批次生圖" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "合成成片" })).not.toBeInTheDocument();
    unmount();

    // 2. Video tab — 既無批次生圖，也無合成（合成已移至成品 tab）
    const { unmount: unmountVideo } = renderActions(
      <EpisodeActionsBar
        projectName="demo"
        episode={1}
        scriptFile="scripts/episode_1.json"
        hasScript
        activeTab="video"
      />
    );
    expect(screen.queryByRole("button", { name: "批次生圖" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "批次生成影片" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "合成成片" })).not.toBeInTheDocument();
    unmountVideo();
  });

  it("renders the compose action only on the final tab", () => {
    renderActions(
      <EpisodeActionsBar
        projectName="demo"
        episode={1}
        scriptFile="scripts/episode_1.json"
        hasScript
        activeTab="final"
      />
    );
    expect(screen.getByRole("button", { name: "合成成片" })).toBeInTheDocument();
    // 成品 tab 不顯示劇本/分鏡相關動作
    expect(screen.queryByRole("button", { name: "批次生圖" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "生成劇本" })).not.toBeInTheDocument();
  });

  it("passes the custom script instruction to generateEpisodeScript", async () => {
    renderTimelineActions();

    // 提示詞框預設收合，點開後輸入
    fireEvent.click(screen.getByRole("button", { name: /劇本提示詞/ }));
    const textarea = await screen.findByLabelText(/劇本生成提示詞/);
    fireEvent.change(textarea, { target: { value: "語氣輕鬆詼諧" } });

    fireEvent.click(screen.getByRole("button", { name: "生成劇本" }));
    // 生成會跳確認框
    fireEvent.click(await screen.findByRole("button", { name: "確定" }));

    await waitFor(() => {
      expect(API.generateEpisodeScript).toHaveBeenCalledWith(
        "demo",
        1,
        undefined,
        "語氣輕鬆詼諧",
      );
    });
  });

  it("persists the script instruction per episode in localStorage", async () => {
    renderTimelineActions();

    fireEvent.click(screen.getByRole("button", { name: /劇本提示詞/ }));
    const textarea = await screen.findByLabelText(/劇本生成提示詞/);
    fireEvent.change(textarea, { target: { value: "強調主角內心戲" } });

    expect(localStorage.getItem("arcreel:script_instruction:demo:1")).toBe("強調主角內心戲");
  });
});
