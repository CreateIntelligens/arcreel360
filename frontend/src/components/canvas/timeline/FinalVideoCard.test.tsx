import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { API } from "@/api";
import { useAppStore } from "@/stores/app-store";
import { FinalVideoCard } from "./FinalVideoCard";

vi.mock("@/api", () => ({
  API: {
    getFileUrl: vi.fn((projectName: string, path: string) => `/api/v1/files/${projectName}/${path}`),
    listFiles: vi.fn(),
  },
}));

vi.mock("@/components/canvas/timeline/VersionTimeMachine", () => ({
  VersionTimeMachine: ({
    resourceType,
    resourceId,
    onRestore,
  }: {
    resourceType: string;
    resourceId: string;
    onRestore?: (version: number) => void | Promise<void>;
  }) => (
    <button
      type="button"
      data-testid="final-video-version-time-machine"
      data-resource-type={resourceType}
      data-resource-id={resourceId}
      onClick={() => void onRestore?.(1)}
    >
      versions
    </button>
  ),
}));

describe("FinalVideoCard", () => {
  beforeEach(() => {
    useAppStore.setState(useAppStore.getInitialState(), true);
    vi.mocked(API.listFiles).mockReset();
    vi.mocked(API.getFileUrl).mockClear();
  });

  it("shows a single legacy final output when the deterministic episode file is missing", async () => {
    vi.mocked(API.listFiles).mockResolvedValue({
      files: {
        output: [
          {
            name: "第一章：午後的回憶_final.mp4",
            size: 1024 * 1024,
            url: "/api/v1/files/demo/output/第一章：午後的回憶_final.mp4",
          },
        ],
      },
    });

    render(<FinalVideoCard projectName="demo" episode={1} />);

    expect(await screen.findByText("第一章：午後的回憶_final.mp4")).toBeInTheDocument();
    await waitFor(() => {
      expect(API.getFileUrl).toHaveBeenCalledWith("demo", "output/第一章：午後的回憶_final.mp4");
    });
  });

  it("mounts output version management for deterministic final videos and refreshes after restore", async () => {
    vi.mocked(API.listFiles).mockResolvedValue({
      files: {
        output: [
          {
            name: "episode_1_final.mp4",
            size: 1024 * 1024,
            url: "/api/v1/files/demo/output/episode_1_final.mp4",
          },
        ],
      },
    });

    render(<FinalVideoCard projectName="demo" episode={1} />);

    expect(await screen.findByText("episode_1_final.mp4")).toBeInTheDocument();
    const versionControl = screen.getByTestId("final-video-version-time-machine");
    expect(versionControl).toHaveAttribute("data-resource-type", "output");
    expect(versionControl).toHaveAttribute("data-resource-id", "1");

    fireEvent.click(versionControl);

    await waitFor(() => {
      expect(API.listFiles).toHaveBeenCalledTimes(2);
    });
  });
});
