import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { API } from "@/api";
import { ConfirmProvider } from "@/components/ui/ConfirmProvider";
import { OverviewCanvas } from "./OverviewCanvas";
import { useAppStore } from "@/stores/app-store";
import { useProjectsStore } from "@/stores/projects-store";
import type { ProjectData } from "@/types";

vi.mock("./WelcomeCanvas", () => ({
  WelcomeCanvas: () => <div data-testid="welcome-canvas">welcome</div>,
}));

function makeProjectData(overrides: Partial<ProjectData> = {}): ProjectData {
  return {
    title: "Demo",
    content_mode: "narration",
    style: "Anime",
    style_description: "old description",
    overview: {
      synopsis: "summary",
      genre: "fantasy",
      theme: "growth",
      world_setting: "palace",
    },
    episodes: [{ episode: 1, title: "EP1", script_file: "scripts/episode_1.json" }],
    characters: {},
    clues: {},
    ...overrides,
  };
}

function renderOverviewCanvas(ui: ReactElement) {
  return render(ui, { wrapper: ConfirmProvider });
}

describe("OverviewCanvas", () => {
  beforeEach(() => {
    useAppStore.setState(useAppStore.getInitialState(), true);
    useProjectsStore.setState(useProjectsStore.getInitialState(), true);
    vi.restoreAllMocks();
    vi.stubGlobal("confirm", vi.fn(() => true));
  });

  it("uploads and deletes the style reference image from the workspace", async () => {
    vi.spyOn(API, "uploadStyleImage").mockResolvedValue({
      success: true,
      style_image: "style_reference.png",
      style_description: "updated",
      url: "u",
    });
    vi.spyOn(API, "deleteStyleImage").mockResolvedValue({ success: true });
    vi.spyOn(API, "getProject")
      .mockResolvedValueOnce({
        project: makeProjectData({ style_image: "style_reference.png" }),
        scripts: {},
      })
      .mockResolvedValueOnce({
        project: makeProjectData(),
        scripts: {},
      });

    const { container, rerender } = renderOverviewCanvas(
      <OverviewCanvas projectName="demo" projectData={makeProjectData()} />,
    );

    const file = new File(["style"], "style.png", { type: "image/png" });
    const fileInput = container.querySelector("input[type='file']");
    expect(fileInput).not.toBeNull();

    fireEvent.change(fileInput as HTMLInputElement, { target: { files: [file] } });

    await waitFor(() => {
      expect(API.uploadStyleImage).toHaveBeenCalledWith("demo", file);
      expect(API.getProject).toHaveBeenCalledTimes(1);
    });

    rerender(
      <OverviewCanvas
        projectName="demo"
        projectData={makeProjectData({ style_image: "style_reference.png" })}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "刪除參考圖" }));
    fireEvent.click(screen.getByRole("button", { name: "確定" }));

    await waitFor(() => {
      expect(API.deleteStyleImage).toHaveBeenCalledWith("demo");
      expect(API.getProject).toHaveBeenCalledTimes(2);
    });
  }, 10_000);

  it("shows a generate-overview action when the project has episodes but no overview", async () => {
    vi.spyOn(API, "generateOverview").mockResolvedValue({
      success: true,
      overview: {
        synopsis: "summary",
        genre: "fantasy",
        theme: "growth",
        world_setting: "palace",
      },
    });
    vi.spyOn(API, "getProject").mockResolvedValue({
      project: makeProjectData(),
      scripts: {},
    });

    // 有劇集但無 overview —— 不應落入 WelcomeCanvas，且概述入口仍須可見
    renderOverviewCanvas(
      <OverviewCanvas
        projectName="demo"
        projectData={makeProjectData({ overview: undefined })}
      />,
    );

    expect(screen.queryByTestId("welcome-canvas")).not.toBeInTheDocument();
    expect(screen.getByText("專案概述")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "生成概述" }));

    await waitFor(() => {
      expect(API.generateOverview).toHaveBeenCalledWith("demo", {
        model: null,
        instruction: null,
      });
    });
  });

  it("shows a save action only when style description is edited", async () => {
    vi.spyOn(API, "updateStyleDescription").mockResolvedValue({ success: true });
    vi.spyOn(API, "getProject").mockResolvedValue({
      project: makeProjectData({ style_description: "new description" }),
      scripts: {},
    });

    renderOverviewCanvas(
      <OverviewCanvas projectName="demo" projectData={makeProjectData()} />,
    );

    expect(
      screen.queryByRole("button", { name: "儲存風格描述" }),
    ).not.toBeInTheDocument();

    fireEvent.change(
      screen.getByPlaceholderText(
        "上傳風格參考圖後，系統會自動分析並填入風格描述；也可以手動編輯。",
      ),
      {
        target: { value: "new description" },
      },
    );

    fireEvent.click(screen.getByRole("button", { name: "儲存風格描述" }));

    await waitFor(() => {
      expect(API.updateStyleDescription).toHaveBeenCalledWith(
        "demo",
        "new description",
      );
      expect(API.getProject).toHaveBeenCalled();
    });
  });

  it("updates the project style using the style select dropdown", async () => {
    vi.spyOn(API, "updateStyle").mockResolvedValue({ success: true });
    vi.spyOn(API, "getProject").mockResolvedValue({
      project: makeProjectData({ style: "3D Animation" }),
      scripts: {},
    });

    renderOverviewCanvas(
      <OverviewCanvas projectName="demo" projectData={makeProjectData()} />,
    );

    const select = screen.getByLabelText("風格標籤：");
    expect(select).toBeInTheDocument();
    expect(select).toHaveValue("Anime");

    fireEvent.change(select, { target: { value: "3D Animation" } });

    await waitFor(() => {
      expect(API.updateStyle).toHaveBeenCalledWith("demo", "3D Animation");
      expect(API.getProject).toHaveBeenCalled();
    });
  });
});
