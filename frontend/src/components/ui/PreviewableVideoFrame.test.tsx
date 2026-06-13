import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PreviewableVideoFrame } from "./PreviewableVideoFrame";

describe("PreviewableVideoFrame", () => {
  it("opens a fullscreen video preview and closes from both the close button and backdrop", () => {
    render(
      <PreviewableVideoFrame src="/demo.mp4" alt="示例影片">
        <video src="/demo.mp4" />
      </PreviewableVideoFrame>,
    );

    const trigger = screen.getByRole("button", { name: "示例影片 全屏預覽" });

    fireEvent.click(trigger);
    expect(
      screen.getByRole("dialog", { name: "示例影片 全屏預覽" }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "關閉影片預覽" }));
    expect(
      screen.queryByRole("dialog", { name: "示例影片 全屏預覽" }),
    ).not.toBeInTheDocument();

    fireEvent.click(trigger);
    const dialog = screen.getByRole("dialog", { name: "示例影片 全屏預覽" });
    const backdrop = dialog.parentElement?.parentElement;
    expect(backdrop).not.toBeNull();

    fireEvent.click(backdrop as HTMLElement);

    expect(
      screen.queryByRole("dialog", { name: "示例影片 全屏預覽" }),
    ).not.toBeInTheDocument();
  }, 10_000);
});
