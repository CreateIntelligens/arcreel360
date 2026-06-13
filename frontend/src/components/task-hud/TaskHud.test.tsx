import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { API } from "@/api";
import { TaskHud } from "@/components/task-hud/TaskHud";
import { useAppStore } from "@/stores/app-store";
import { useTasksStore } from "@/stores/tasks-store";
import type { TaskItem, TaskStats } from "@/types";

function makeTask(overrides: Partial<TaskItem> = {}): TaskItem {
  return {
    task_id: "task-1",
    project_name: "demo",
    task_type: "storyboard",
    media_type: "image",
    resource_id: "S01",
    script_file: null,
    payload: {},
    status: "queued",
    result: null,
    error_message: null,
    source: "webui",
    queued_at: "2026-02-01T00:00:00Z",
    started_at: null,
    finished_at: null,
    updated_at: "2026-02-01T00:00:00Z",
    ...overrides,
  };
}

function makeStats(overrides: Partial<TaskStats> = {}): TaskStats {
  return {
    queued: 0,
    running: 0,
    succeeded: 0,
    failed: 0,
    cancelled: 0,
    total: 0,
    ...overrides,
  };
}

function renderOpenHud() {
  const anchor = document.createElement("button");
  document.body.appendChild(anchor);
  return render(<TaskHud anchorRef={{ current: anchor }} />);
}

describe("TaskHud cancellation", () => {
  beforeEach(() => {
    useAppStore.setState(useAppStore.getInitialState(), true);
    useTasksStore.setState(useTasksStore.getInitialState(), true);
    useAppStore.getState().setTaskHudOpen(true);
  });

  it("previews and confirms a queued task cancellation", async () => {
    useTasksStore.setState({
      tasks: [makeTask()],
      stats: makeStats({ queued: 1, total: 1 }),
      connected: true,
    });
    const previewSpy = vi.spyOn(API, "cancelPreview").mockResolvedValue({
      task: { task_id: "task-1", task_type: "storyboard", resource_id: "S01" },
      cascaded: [],
    });
    const cancelSpy = vi.spyOn(API, "cancelTask").mockResolvedValue({
      cancelled: [makeTask({ status: "cancelled", cancelled_by: "user" })],
      skipped_running: [],
    });

    renderOpenHud();

    fireEvent.click(screen.getByLabelText("取消任務 S01"));

    await screen.findByText("確定取消此任務？");
    fireEvent.click(screen.getByRole("button", { name: "確認取消" }));

    await waitFor(() => expect(cancelSpy).toHaveBeenCalledWith("task-1"));
    expect(previewSpy).toHaveBeenCalledWith("task-1");
    expect(screen.getByText("已取消")).toBeInTheDocument();
  });

  it("shows cancelled cascade tasks", () => {
    useTasksStore.setState({
      tasks: [makeTask({ status: "cancelled", cancelled_by: "cascade" })],
      stats: makeStats({ cancelled: 1, total: 1 }),
      connected: true,
    });

    renderOpenHud();

    expect(screen.getByText("已取消")).toBeInTheDocument();
    expect(screen.getByText("級聯")).toBeInTheDocument();
  });
});
