import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Router, useLocation, useSearch } from "wouter";
import { memoryLocation } from "wouter/memory-location";
import { GlobalHeader } from "@/components/layout/GlobalHeader";
import { API } from "@/api";
import { useAppStore } from "@/stores/app-store";
import { useAssistantStore } from "@/stores/assistant-store";
import { useProjectsStore } from "@/stores/projects-store";
import { useTasksStore } from "@/stores/tasks-store";
import { useUsageStore } from "@/stores/usage-store";

vi.mock("@/components/task-hud/TaskHud", () => ({
  TaskHud: () => <div data-testid="task-hud" />,
}));

vi.mock("./UsageDrawer", () => ({
  UsageDrawer: () => <div data-testid="usage-drawer" />,
}));

vi.mock("./WorkspaceNotificationsDrawer", () => ({
  WorkspaceNotificationsDrawer: ({ open }: { open: boolean }) =>
    open ? <div data-testid="notifications-drawer" /> : null,
}));

vi.mock("./ExportScopeDialog", () => ({
  ExportScopeDialog: ({
    open,
    onSelect,
  }: {
    open: boolean;
    onClose: () => void;
    onSelect: (scope: "current" | "full") => void;
    anchorRef: React.RefObject<HTMLElement | null>;
    episodes?: unknown[];
    onJianyingExport?: (episode: number, draftPath: string, jianyingVersion: string) => void;
    jianyingExporting?: boolean;
  }) =>
    open ? (
      <div data-testid="export-scope-dialog">
        <button data-testid="scope-current" onClick={() => onSelect("current")}>
          僅目前版本
        </button>
        <button data-testid="scope-full" onClick={() => onSelect("full")}>
          全部資料
        </button>
      </div>
    ) : null,
}));

function LocationProbe() {
  const [location] = useLocation();
  const search = useSearch();
  return <div data-testid="location">{search ? `${location}?${search}` : location}</div>;
}

function renderHeader(path = "/characters") {
  const { hook } = memoryLocation({ path });
  return render(
    <Router hook={hook}>
      <LocationProbe />
      <GlobalHeader />
    </Router>,
  );
}

describe("GlobalHeader", () => {
  beforeEach(() => {
    useProjectsStore.setState(useProjectsStore.getInitialState(), true);
    useAppStore.setState(useAppStore.getInitialState(), true);
    useAssistantStore.setState(useAssistantStore.getInitialState(), true);
    useTasksStore.setState(useTasksStore.getInitialState(), true);
    useUsageStore.setState(useUsageStore.getInitialState(), true);
    vi.restoreAllMocks();
  });

  it("prefers the project title over the internal project name", async () => {
    vi.spyOn(API, "getUsageStats").mockResolvedValue({
      total_cost: 0,
      image_count: 0,
      video_count: 0,
      failed_count: 0,
      total_count: 0,
    });

    useProjectsStore.setState({
      currentProjectName: "halou-92d19a04",
      currentProjectData: {
        title: "哈嘍專案",
        content_mode: "narration",
        style: "Anime",
        episodes: [],
        characters: {},
        clues: {},
      },
    });

    renderHeader();

    expect(screen.getByText("哈嘍專案")).toBeInTheDocument();
    expect(screen.queryByText("halou-92d19a04")).not.toBeInTheDocument();

    await waitFor(() => {
      expect(API.getUsageStats).toHaveBeenCalledWith({
        projectName: "halou-92d19a04",
      });
    });
  });

  it("shows unread notification count and opens the drawer", async () => {
    vi.spyOn(API, "getUsageStats").mockResolvedValue({
      total_cost: 0,
      image_count: 0,
      video_count: 0,
      failed_count: 0,
      total_count: 0,
    });

    useAppStore.getState().pushWorkspaceNotification({
      text: "AI 剛更新了線索「玉佩」，點選檢視",
      target: {
        type: "clue",
        id: "玉佩",
        route: "/clues",
      },
    });

    renderHeader();

    expect(screen.getByTitle("會話通知：1 則")).toBeInTheDocument();
    screen.getByRole("button", { name: "開啟通知中心" }).click();
    expect(await screen.findByTestId("notifications-drawer")).toBeInTheDocument();
  });

  it("lets the timeline choose the remembered tab when navigating to scripting", async () => {
    vi.spyOn(API, "getUsageStats").mockResolvedValue({
      total_cost: 0,
      image_count: 0,
      video_count: 0,
      failed_count: 0,
      total_count: 0,
    });

    useProjectsStore.setState({
      currentProjectName: "demo",
      currentProjectData: {
        title: "Demo",
        content_mode: "narration",
        style: "Anime",
        episodes: [{ episode: 1, title: "第一集", script_file: "scripts/episode_1.json" }],
        characters: {},
        clues: {},
      },
    });

    renderHeader();

    screen.getByRole("button", { name: /劇本創作/ }).click();

    await waitFor(() => {
      expect(screen.getByTestId("location")).toHaveTextContent("/episodes/1");
    });
    expect(screen.getByTestId("location")).not.toHaveTextContent("tab=preprocessing");
  });

  it("exports the current project zip via browser-native download", async () => {
    vi.spyOn(API, "getUsageStats").mockResolvedValue({
      total_cost: 0,
      image_count: 0,
      video_count: 0,
      failed_count: 0,
      total_count: 0,
    });
    vi.spyOn(API, "requestExportToken").mockResolvedValue({
      download_token: "test-download-token",
      expires_in: 300,
      diagnostics: {
        blocking: [],
        auto_fixed: [{ code: "current_asset_restored_from_version", message: "修復影片引用" }],
        warnings: [],
      },
    });
    const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    useProjectsStore.setState({
      currentProjectName: "demo",
      currentProjectData: {
        title: "匯出專案",
        content_mode: "narration",
        style: "Anime",
        episodes: [],
        characters: {},
        clues: {},
      },
    });

    renderHeader();
    // Click export button to open dialog
    screen.getByRole("button", { name: "匯出目前專案 ZIP" }).click();

    // Wait for dialog to appear then click "僅目前版本"
    const scopeBtn = await screen.findByTestId("scope-current");
    scopeBtn.click();

    await waitFor(() => {
      expect(API.requestExportToken).toHaveBeenCalledWith("demo", "current");
    });
    expect(anchorClick).toHaveBeenCalled();
    expect(useAppStore.getState().toast?.text).toContain("包含 1 筆診斷");
  });

  it("shows an error toast when exporting fails", async () => {
    vi.spyOn(API, "getUsageStats").mockResolvedValue({
      total_cost: 0,
      image_count: 0,
      video_count: 0,
      failed_count: 0,
      total_count: 0,
    });
    vi.spyOn(API, "requestExportToken").mockRejectedValue(new Error("network"));

    useProjectsStore.setState({
      currentProjectName: "demo",
      currentProjectData: {
        title: "匯出專案",
        content_mode: "narration",
        style: "Anime",
        episodes: [],
        characters: {},
        clues: {},
      },
    });

    renderHeader();
    screen.getByRole("button", { name: "匯出目前專案 ZIP" }).click();

    const scopeBtn = await screen.findByTestId("scope-full");
    scopeBtn.click();

    await waitFor(() => {
      expect(useAppStore.getState().toast?.text).toContain("匯出失敗");
    });
  });
});
