import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { WelcomeCanvas } from "@/components/canvas/WelcomeCanvas";
import { API } from "@/api";
import { useAppStore } from "@/stores/app-store";

describe("WelcomeCanvas", () => {
  beforeEach(() => {
    useAppStore.setState(useAppStore.getInitialState(), true);
    vi.restoreAllMocks();
  });

  it("shows the project title instead of the internal project name", async () => {
    vi.spyOn(API, "listFiles").mockResolvedValue({ files: { source: [] } });

    render(
      <WelcomeCanvas
        projectName="halou-92d19a04"
        projectTitle="哈嘍專案"
      />,
    );

    expect(await screen.findByText("歡迎來到 哈嘍專案！")).toBeInTheDocument();
    expect(screen.queryByText("歡迎來到 halou-92d19a04！")).not.toBeInTheDocument();
  });

  it("accepts Word source files from the overview drop zone", async () => {
    vi.spyOn(API, "listFiles").mockResolvedValue({ files: { source: [] } });
    const onUpload = vi.fn().mockResolvedValue(undefined);

    render(<WelcomeCanvas projectName="demo" onUpload={onUpload} />);

    const dropZone = await screen.findByRole("button", { name: /拖曳檔案到此處/ });
    const file = new File(["hello"], "story.docx", {
      type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    });
    fireEvent.drop(dropZone, {
      dataTransfer: {
        files: [file],
      },
    });

    await waitFor(() => expect(onUpload).toHaveBeenCalledWith(file));
  });

  it("uses the same source file picker accept list in both overview upload states", async () => {
    vi.spyOn(API, "listFiles").mockResolvedValue({
      files: { source: [{ name: "story.docx", size: 12, url: "/files/story.docx" }] },
    });

    const { rerender } = render(<WelcomeCanvas projectName="demo" />);

    expect(await screen.findByText("story.docx")).toBeInTheDocument();
    expect(document.querySelector("input[type='file']")).toHaveAttribute("accept", ".txt,.md,.doc,.docx");

    vi.mocked(API.listFiles).mockResolvedValue({ files: { source: [] } });
    rerender(<WelcomeCanvas projectName="other-demo" />);

    await screen.findByText("拖曳檔案到此處");
    expect(document.querySelector("input[type='file']")).toHaveAttribute("accept", ".txt,.md,.doc,.docx");
  });
});
