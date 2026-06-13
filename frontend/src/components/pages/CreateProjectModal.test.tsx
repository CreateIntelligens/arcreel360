import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Router } from "wouter";
import { memoryLocation } from "wouter/memory-location";
import { API } from "@/api";
import { CreateProjectModal } from "@/components/pages/CreateProjectModal";
import { useAppStore } from "@/stores/app-store";
import { useProjectsStore } from "@/stores/projects-store";

function renderModal() {
  const location = memoryLocation({ path: "/app/projects" });
  return render(
    <Router hook={location.hook}>
      <CreateProjectModal />
    </Router>,
  );
}

describe("CreateProjectModal", () => {
  beforeEach(() => {
    useProjectsStore.setState(useProjectsStore.getInitialState(), true);
    useProjectsStore.setState({ showCreateModal: true });
    useAppStore.setState(useAppStore.getInitialState(), true);
    vi.restoreAllMocks();
  });

  it("submits only the project title and uses backend-generated name", async () => {
    vi.spyOn(API, "createProject").mockResolvedValue({
      success: true,
      name: "project-aa11bb22",
      project: {
        title: "演示專案",
        content_mode: "narration",
        style: "Photographic",
        episodes: [],
        characters: {},
        clues: {},
      },
    });

    renderModal();

    const submitButton = screen.getByRole("button", { name: "建立專案" });
    expect(submitButton).toBeDisabled();

    fireEvent.change(screen.getByPlaceholderText("例如：重生之皇後威武"), {
      target: { value: "演示專案" },
    });

    expect(submitButton).toBeEnabled();
    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(API.createProject).toHaveBeenCalledWith("演示專案", "Photographic", "narration", "9:16", null);
    });
  });

  it("disables submission when the project title is empty", () => {
    vi.spyOn(API, "createProject").mockResolvedValue({
      success: true,
      name: "project-aa11bb22",
      project: {
        title: "演示專案",
        content_mode: "narration",
        style: "Photographic",
        episodes: [],
        characters: {},
        clues: {},
      },
    });

    renderModal();

    expect(screen.getByRole("button", { name: "建立專案" })).toBeDisabled();
    expect(API.createProject).not.toHaveBeenCalled();
  });

  it("does not render project-level default duration controls", () => {
    renderModal();

    expect(screen.queryByText("預設時長")).not.toBeInTheDocument();
    expect(screen.queryByRole("radiogroup", { name: "預設時長" })).not.toBeInTheDocument();
  });
});
