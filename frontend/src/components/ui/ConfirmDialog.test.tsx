import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ConfirmDialog } from "./ConfirmDialog";

describe("ConfirmDialog", () => {
  it("does not render when open=false", () => {
    render(
      <ConfirmDialog
        open={false}
        message="hello"
        onConfirm={() => {}}
        onCancel={() => {}}
      />,
    );
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  it("renders title, message and default labels when open", () => {
    render(
      <ConfirmDialog
        open
        title="刪除確認"
        message="確定要刪除？"
        onConfirm={() => {}}
        onCancel={() => {}}
      />,
    );
    expect(screen.getByRole("alertdialog")).toBeInTheDocument();
    expect(screen.getByText("刪除確認")).toBeInTheDocument();
    expect(screen.getByText("確定要刪除？")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "確定" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "取消" })).toBeInTheDocument();
  });

  it("invokes onConfirm when confirm button clicked", () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(
      <ConfirmDialog
        open
        message="確定？"
        onConfirm={onConfirm}
        onCancel={onCancel}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "確定" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onCancel).not.toHaveBeenCalled();
  });

  it("invokes onCancel when cancel button clicked", () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(
      <ConfirmDialog
        open
        message="確定？"
        onConfirm={onConfirm}
        onCancel={onCancel}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("invokes onCancel on ESC key and onConfirm on Enter", () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(
      <ConfirmDialog
        open
        message="確定？"
        onConfirm={onConfirm}
        onCancel={onCancel}
      />,
    );
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onCancel).toHaveBeenCalledTimes(1);

    fireEvent.keyDown(window, { key: "Enter" });
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("does not respond to keys when closed", () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(
      <ConfirmDialog
        open={false}
        message="確定？"
        onConfirm={onConfirm}
        onCancel={onCancel}
      />,
    );
    fireEvent.keyDown(window, { key: "Escape" });
    fireEvent.keyDown(window, { key: "Enter" });
    expect(onCancel).not.toHaveBeenCalled();
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("uses custom labels", () => {
    render(
      <ConfirmDialog
        open
        message="m"
        confirmLabel="刪除"
        cancelLabel="算了"
        onConfirm={() => {}}
        onCancel={() => {}}
      />,
    );
    expect(screen.getByRole("button", { name: "刪除" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "算了" })).toBeInTheDocument();
  });

  it("dismisses on backdrop click by default", () => {
    const onCancel = vi.fn();
    const { container } = render(
      <ConfirmDialog
        open
        message="確定？"
        onConfirm={() => {}}
        onCancel={onCancel}
      />,
    );
    // 第一個 <div role="presentation"> 是背景
    const backdrop = container.querySelector('[role="presentation"]');
    expect(backdrop).not.toBeNull();
    fireEvent.click(backdrop!);
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("does not dismiss on backdrop click when dismissOnBackdrop=false", () => {
    const onCancel = vi.fn();
    const { container } = render(
      <ConfirmDialog
        open
        message="確定？"
        dismissOnBackdrop={false}
        onConfirm={() => {}}
        onCancel={onCancel}
      />,
    );
    const backdrop = container.querySelector('[role="presentation"]');
    fireEvent.click(backdrop!);
    expect(onCancel).not.toHaveBeenCalled();
  });
});
