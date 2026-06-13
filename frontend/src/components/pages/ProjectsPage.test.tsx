import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Router } from "wouter";
import { memoryLocation } from "wouter/memory-location";
import { API } from "@/api";
import { useAppStore } from "@/stores/app-store";
import { useProjectsStore } from "@/stores/projects-store";
import { ProjectsPage } from "@/components/pages/ProjectsPage";
import type { ProjectSummary } from "@/types";

vi.mock("@/components/pages/CreateProjectModal", () => ({
  CreateProjectModal: () => <div data-testid="create-project-modal">Create Project Modal</div>,
}));

function renderPage() {
  const location = memoryLocation({ path: "/app/projects", record: true });
  return {
    ...render(
      <Router hook={location.hook}>
        <ProjectsPage />
      </Router>,
    ),
    location,
  };
}

function makeProjectSummary(overrides: Partial<ProjectSummary> = {}): ProjectSummary {
  return {
    name: "demo",
    title: "Demo Project",
    style: "Anime",
    thumbnail: null,
    status: {
      current_phase: "setup",
      phase_progress: 0.1,
      characters: { total: 0, completed: 0 },
      clues: { total: 0, completed: 0 },
      scenes: { total: 0, completed: 0 },
      episodes_summary: { total: 0, scripted: 0, in_production: 0, completed: 0 },
    },
    ...overrides,
  };
}

describe("ProjectsPage", () => {
  beforeEach(() => {
    useProjectsStore.setState(useProjectsStore.getInitialState(), true);
    useAppStore.setState(useAppStore.getInitialState(), true);
    vi.restoreAllMocks();
  });

  it("shows loading state while projects are being fetched", () => {
    vi.spyOn(API, "listProjects").mockImplementation(
      () => new Promise(() => {}),
    );

    renderPage();
    expect(screen.getByText("載入專案列表...")).toBeInTheDocument();
  });

  it("shows empty state when no projects exist", async () => {
    vi.spyOn(API, "listProjects").mockResolvedValue({ projects: [] });

    renderPage();

    expect(await screen.findByText("暫無專案")).toBeInTheDocument();
    expect(
      screen.getByText("點選右上角「新建專案」或「匯入 ZIP」開始創作"),
    ).toBeInTheDocument();
  });

  it("renders project cards when data exists", async () => {
    vi.spyOn(API, "listProjects").mockResolvedValue({
      projects: [
        {
          name: "demo",
          title: "Demo Project",
          style: "Anime",
          thumbnail: null,
          status: {
            current_phase: "storyboard",
            phase_progress: 0.5,
            characters: { total: 2, completed: 2 },
            clues: { total: 2, completed: 1 },
            scenes: { total: 0, completed: 0 },
            episodes_summary: { total: 1, scripted: 1, in_production: 1, completed: 0 },
          },
        },
      ],
    });

    renderPage();

    expect(await screen.findByText("Demo Project")).toBeInTheDocument();
    expect(screen.getByText("Anime · 分鏡圖")).toBeInTheDocument();
    expect(screen.getByText("50%")).toBeInTheDocument();
  });

  it("opens create project modal after clicking new project button", async () => {
    vi.spyOn(API, "listProjects").mockResolvedValue({ projects: [] });

    renderPage();
    await screen.findByText("暫無專案");

    fireEvent.click(screen.getByRole("button", { name: "新建專案" }));

    await waitFor(() => {
      expect(useProjectsStore.getState().showCreateModal).toBe(true);
    });
    expect(screen.getByTestId("create-project-modal")).toBeInTheDocument();
  });

  it("imports a zip project, refreshes the list, and navigates to the workspace", async () => {
    vi.spyOn(API, "listProjects")
      .mockResolvedValueOnce({ projects: [] })
      .mockResolvedValueOnce({
        projects: [
          {
            name: "imported-demo",
            title: "Imported Demo",
            style: "Anime",
            thumbnail: null,
            status: {
              current_phase: "completed",
              phase_progress: 1,
              characters: { total: 1, completed: 1 },
              clues: { total: 1, completed: 1 },
              scenes: { total: 0, completed: 0 },
              episodes_summary: { total: 1, scripted: 1, in_production: 0, completed: 1 },
            },
          },
        ],
      });
    vi.spyOn(API, "importProject").mockResolvedValue({
      success: true,
      project_name: "imported-demo",
      project: {
        title: "Imported Demo",
        content_mode: "narration",
        style: "Anime",
        episodes: [],
        characters: {},
        clues: {},
      },
      warnings: ["發現未識別的附加檔案/目錄: extras"],
      conflict_resolution: "none",
      diagnostics: {
        auto_fixed: [{ code: "missing_clues_field", message: "segments[0]: 補全缺失欄位 clues_in_segment" }],
        warnings: [{ code: "validation_warning", message: "發現未識別的附加檔案/目錄: extras" }],
      },
    });

    const { container, location } = renderPage();
    await screen.findByText("暫無專案");

    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["zip"], "project.zip", { type: "application/zip" });
    fireEvent.change(fileInput, { target: { files: [file] } });

    await waitFor(() => {
      expect(API.importProject).toHaveBeenCalledWith(file, "prompt");
    });
    await waitFor(() => {
      expect(location.history?.at(-1)).toBe("/app/projects/imported-demo");
    });
    expect(useAppStore.getState().toast?.text).toContain("匯入警告");
  });

  it("shows a structured toast when import fails", async () => {
    vi.spyOn(API, "listProjects").mockResolvedValue({ projects: [] });
    const error = new Error("匯入包校驗失敗") as Error & {
      detail?: string;
      errors?: string[];
      warnings?: string[];
      diagnostics?: {
        blocking: { code: string; message: string }[];
        auto_fixable: { code: string; message: string }[];
        warnings: { code: string; message: string }[];
      };
    };
    error.detail = "匯入包校驗失敗";
    error.errors = ["缺少 project.json", "缺少 scripts/episode_1.json", "缺少角色圖"];
    error.warnings = ["發現未識別的附加檔案／目錄：extras"];
    error.diagnostics = {
      blocking: [
        { code: "validation_error", message: "缺少 project.json" },
        { code: "validation_error", message: "缺少 scripts/episode_1.json" },
      ],
      auto_fixable: [
        { code: "missing_clues_field", message: "segments[0]: 補齊缺失欄位 clues_in_segment" },
      ],
      warnings: [
        { code: "validation_warning", message: "發現未識別的附加檔案／目錄：extras" },
      ],
    };
    vi.spyOn(API, "importProject").mockRejectedValue(error);

    const { container } = renderPage();
    await screen.findByText("暫無專案");

    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(fileInput, {
      target: { files: [new File(["zip"], "broken.zip", { type: "application/zip" })] },
    });

    await waitFor(() => {
      expect(useAppStore.getState().toast?.text).toContain("匯入包校驗失敗");
    });
    expect(screen.getByText("匯入診斷")).toBeInTheDocument();
    expect(screen.getByText("缺少 project.json")).toBeInTheDocument();
    expect(screen.getByText("缺少 scripts/episode_1.json")).toBeInTheDocument();
    expect(screen.getByText("segments[0]: 補齊缺失欄位 clues_in_segment")).toBeInTheDocument();
  });

  it("opens a secondary confirmation when import hits a duplicate project id", async () => {
    vi.spyOn(API, "listProjects")
      .mockResolvedValueOnce({ projects: [] })
      .mockResolvedValueOnce({
        projects: [
          {
            name: "demo",
            title: "Demo",
            style: "Anime",
            thumbnail: null,
            status: {
              current_phase: "completed",
              phase_progress: 1,
              characters: { total: 1, completed: 1 },
              clues: { total: 1, completed: 1 },
              scenes: { total: 0, completed: 0 },
              episodes_summary: { total: 1, scripted: 1, in_production: 0, completed: 1 },
            },
          },
        ],
      });
    const conflictError = new Error("偵測到專案編號衝突") as Error & {
      status?: number;
      detail?: string;
      errors?: string[];
      conflict_project_name?: string;
    };
    conflictError.status = 409;
    conflictError.detail = "偵測到專案編號衝突";
    conflictError.errors = ["專案編號 'demo' 已存在"];
    conflictError.conflict_project_name = "demo";

    vi.spyOn(API, "importProject")
      .mockRejectedValueOnce(conflictError)
      .mockResolvedValueOnce({
        success: true,
        project_name: "demo-renamed",
        project: {
          title: "Renamed Demo",
          content_mode: "narration",
          style: "Anime",
          episodes: [],
          characters: {},
          clues: {},
        },
        warnings: [],
        conflict_resolution: "renamed",
        diagnostics: {
          auto_fixed: [],
          warnings: [],
        },
      });

    const { container, location } = renderPage();
    await screen.findByText("暫無專案");

    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["zip"], "project.zip", { type: "application/zip" });
    fireEvent.change(fileInput, { target: { files: [file] } });

    expect(await screen.findByText("偵測到專案編號重複")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "自動重新命名匯入" }));

    await waitFor(() => {
      expect(API.importProject).toHaveBeenNthCalledWith(1, file, "prompt");
    });
    await waitFor(() => {
      expect(API.importProject).toHaveBeenNthCalledWith(2, file, "rename");
    });
    await waitFor(() => {
      expect(location.history?.at(-1)).toBe("/app/projects/demo-renamed");
    });
  });

  it("opens the delete confirmation dialog, handles deletion, and refreshes the list", async () => {
    vi.spyOn(API, "listProjects")
      .mockResolvedValueOnce({
        projects: [
          makeProjectSummary({
            name: "to-delete",
            title: "Project to Delete",
          }),
        ],
      })
      .mockResolvedValueOnce({ projects: [] });

    const deleteSpy = vi.spyOn(API, "deleteProject").mockResolvedValue({ success: true } as any);

    renderPage();

    expect(await screen.findByText("Project to Delete")).toBeInTheDocument();

    const deleteBtn = screen.getByRole("button", { name: "刪除專案 Project to Delete" });
    fireEvent.click(deleteBtn);

    expect(screen.getByRole("heading", { name: "刪除專案" })).toBeInTheDocument();

    const confirmBtn = screen.getByRole("button", { name: "確認刪除" });
    expect(confirmBtn).toBeDisabled();

    const input = screen.getByPlaceholderText("DELETE");
    fireEvent.change(input, { target: { value: "DELETE" } });
    expect(confirmBtn).not.toBeDisabled();

    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(deleteSpy).toHaveBeenCalledWith("to-delete");
    });

    await waitFor(() => {
      expect(API.listProjects).toHaveBeenCalledTimes(2);
    });

    await waitFor(() => {
      expect(screen.queryByRole("heading", { name: "刪除專案" })).not.toBeInTheDocument();
    });
    expect(await screen.findByText("暫無專案")).toBeInTheDocument();

    expect(useAppStore.getState().toast?.text).toBe("專案「Project to Delete」已刪除");
    expect(useAppStore.getState().toast?.tone).toBe("success");
  });
});
