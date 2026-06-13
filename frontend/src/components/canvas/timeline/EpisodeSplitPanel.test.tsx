import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { API } from "@/api";
import type { EpisodeSplitPeekResponse } from "@/api";
import { useAppStore } from "@/stores/app-store";
import { EpisodeSplitPanel } from "./EpisodeSplitPanel";

vi.mock("@/api", () => ({
  API: {
    peekEpisodeSplit: vi.fn(),
    splitEpisode: vi.fn(),
  },
}));

const peekResult: EpisodeSplitPeekResponse = {
  total_chars: 100,
  target_chars: 50,
  target_offset: 60,
  context_before: "這是一段切點前的測試文字，用來產生錨點",
  context_after: "這是切點後的內容",
  nearby_breakpoints: [
    { offset: 62, char: "。", type: "sentence", distance: 2 },
    { offset: 70, char: "。", type: "sentence", distance: 10 },
  ],
};

function anchorBefore(offset: number): string {
  const contextStart = peekResult.target_offset - peekResult.context_before.length;
  const localCut = offset - contextStart;
  const combinedContext = `${peekResult.context_before}${peekResult.context_after}`;
  return combinedContext.slice(Math.max(0, localCut - 16), localCut);
}

describe("EpisodeSplitPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAppStore.setState({ toast: null, workspaceNotifications: [] });
  });

  it("previews split point, selects a breakpoint, splits, and calls onSplitDone", async () => {
    vi.mocked(API.peekEpisodeSplit).mockResolvedValue(peekResult);
    vi.mocked(API.splitEpisode).mockResolvedValue({
      episode: 1,
      episode_file: "source/episode_1.txt",
      remaining_file: "source/_remaining.txt",
      part_before_chars: 60,
      part_after_chars: 40,
      split_pos: 60,
      anchor_match_count: 1,
    });
    const onSplitDone = vi.fn();

    render(
      <EpisodeSplitPanel
        projectName="demo"
        sourceFiles={["source/novel.txt"]}
        onSplitDone={onSplitDone}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /預覽切點/ }));

    await waitFor(() => {
      expect(API.peekEpisodeSplit).toHaveBeenCalledWith("demo", {
        source: "source/novel.txt",
        target_chars: 3000,
      });
    });
    expect(await screen.findByText(/sentence @ 62/)).toBeInTheDocument();

    fireEvent.click(screen.getAllByRole("button", { name: /選此處/ })[0]);
    fireEvent.click(screen.getByRole("button", { name: /執行切分/ }));

    await waitFor(() => {
      expect(API.splitEpisode).toHaveBeenCalledWith("demo", {
        source: "source/novel.txt",
        episode: 1,
        target_chars: 3000,
        anchor: anchorBefore(peekResult.nearby_breakpoints[0].offset),
      });
    });
    await waitFor(() => expect(onSplitDone).toHaveBeenCalledTimes(1));
    expect(useAppStore.getState().toast?.text).toContain("已切出第 1 集");
    expect(useAppStore.getState().toast?.tone).toBe("success");
  });

  it("shows an error when preview fails", async () => {
    vi.mocked(API.peekEpisodeSplit).mockRejectedValue(new Error("目標字數超過總字數"));

    render(
      <EpisodeSplitPanel
        projectName="demo"
        sourceFiles={["source/n.txt"]}
        onSplitDone={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /預覽切點/ }));

    expect(await screen.findByText(/目標字數超過總字數/)).toBeInTheDocument();
  });
});
