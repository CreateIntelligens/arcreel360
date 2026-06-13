import type { ComponentProps } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DeleteProjectDialog } from "./DeleteProjectDialog";

describe("DeleteProjectDialog", () => {
  type DialogProps = ComponentProps<typeof DeleteProjectDialog>;

  function renderDialog(overrides: Partial<DialogProps> = {}) {
    const props: DialogProps = {
      projectName: "demo-project",
      projectTitle: "Demo Project Title",
      deleting: false,
      onCancel: vi.fn(),
      onConfirm: vi.fn(),
      ...overrides,
    };
    return { ...render(<DeleteProjectDialog {...props} />), props };
  }

  it("renders correctly with project title", () => {
    renderDialog();
    expect(screen.getByText("刪除專案")).toBeInTheDocument();
    expect(screen.getByText(/Demo Project Title/)).toBeInTheDocument();
  });

  it("disables delete button initially", () => {
    renderDialog();
    const confirmButton = screen.getByRole("button", { name: "確認刪除" });
    expect(confirmButton).toBeDisabled();
  });

  it("enables delete button only when typing DELETE", () => {
    renderDialog();
    const input = screen.getByPlaceholderText("DELETE");
    const confirmButton = screen.getByRole("button", { name: "確認刪除" });

    fireEvent.change(input, { target: { value: "DELET" } });
    expect(confirmButton).toBeDisabled();

    fireEvent.change(input, { target: { value: "DELETE" } });
    expect(confirmButton).toBeEnabled();
  });

  it("calls onConfirm when clicking enabled delete button", () => {
    const { props } = renderDialog();
    const input = screen.getByPlaceholderText("DELETE");
    const confirmButton = screen.getByRole("button", { name: "確認刪除" });

    fireEvent.change(input, { target: { value: "DELETE" } });
    fireEvent.click(confirmButton);
    expect(props.onConfirm).toHaveBeenCalledTimes(1);
  });

  it("calls onCancel when clicking cancel button", () => {
    const { props } = renderDialog();
    const cancelButton = screen.getByRole("button", { name: "取消" });

    fireEvent.click(cancelButton);
    expect(props.onCancel).toHaveBeenCalledTimes(1);
  });

  it("calls onCancel when pressing Escape key", () => {
    const { props } = renderDialog();

    fireEvent.keyDown(window, { key: "Escape" });
    expect(props.onCancel).toHaveBeenCalledTimes(1);
  });

  it("shows deleting status and disables controls when deleting is true", () => {
    renderDialog({ deleting: true });

    const input = screen.getByPlaceholderText("DELETE");
    expect(input).toBeDisabled();

    const cancelButton = screen.getByRole("button", { name: "取消" });
    expect(cancelButton).toBeDisabled();

    expect(screen.getByText("刪除中...")).toBeInTheDocument();
  });
});
