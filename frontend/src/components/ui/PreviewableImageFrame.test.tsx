import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PreviewableImageFrame } from "./PreviewableImageFrame";

describe("PreviewableImageFrame", () => {
  it("opens a fullscreen preview and closes from both the close button and backdrop", () => {
    render(
      <PreviewableImageFrame src="/demo.png" alt="示例圖">
        <img src="/demo.png" alt="示例圖" />
      </PreviewableImageFrame>,
    );

    const trigger = screen.getByRole("button", { name: "示例圖 全屏預覽" });

    fireEvent.click(trigger);
    expect(
      screen.getByRole("dialog", { name: "示例圖 全屏預覽" }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "關閉全屏預覽" }));
    expect(
      screen.queryByRole("dialog", { name: "示例圖 全屏預覽" }),
    ).not.toBeInTheDocument();

    fireEvent.click(trigger);
    const dialog = screen.getByRole("dialog", { name: "示例圖 全屏預覽" });
    const backdrop = dialog.parentElement?.parentElement;
    expect(backdrop).not.toBeNull();

    fireEvent.click(backdrop as HTMLElement);

    expect(
      screen.queryByRole("dialog", { name: "示例圖 全屏預覽" }),
    ).not.toBeInTheDocument();
  }, 10_000);
});
