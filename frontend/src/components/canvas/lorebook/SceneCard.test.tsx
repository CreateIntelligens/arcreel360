import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ConfirmProvider } from "@/components/ui/ConfirmProvider";
import { SceneCard } from "./SceneCard";
import { useAppStore } from "@/stores/app-store";

function renderSceneCard(ui: ReactElement) {
  return render(ui, { wrapper: ConfirmProvider });
}

describe("SceneCard", () => {
  beforeEach(() => {
    useAppStore.setState(useAppStore.getInitialState(), true);
    vi.restoreAllMocks();
    Object.defineProperty(globalThis.URL, "createObjectURL", {
      writable: true,
      value: vi.fn(() => "blob:scene-ref"),
    });
    Object.defineProperty(globalThis.URL, "revokeObjectURL", {
      writable: true,
      value: vi.fn(),
    });
  });

  it("renders the scene description", () => {
    renderSceneCard(
      <SceneCard
        name="廢棄醫院"
        scene={{ description: "陰森的走廊" }}
        projectName="demo"
        onSave={vi.fn()}
      />,
    );

    expect(screen.getByText("廢棄醫院")).toBeInTheDocument();
    expect(screen.queryByText("場景")).not.toBeInTheDocument();
    const textarea = screen.getByPlaceholderText("輸入場景描述...");
    expect(textarea).toHaveValue("陰森的走廊");
  });

  it("renders existing saved scene_sheet image", () => {
    renderSceneCard(
      <SceneCard
        name="廢棄醫院"
        scene={{
          description: "陰森的走廊",
          scene_sheet: "scenes/廢棄醫院.png",
        }}
        projectName="demo"
        onSave={vi.fn()}
      />,
    );

    expect(screen.getByAltText("廢棄醫院 設計圖")).toHaveAttribute(
      "src",
      "/api/v1/files/demo/scenes/廢棄醫院.png",
    );
  });

  it("submits description changes through onSave", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    renderSceneCard(
      <SceneCard
        name="廢棄醫院"
        scene={{ description: "陰森的走廊" }}
        projectName="demo"
        onSave={onSave}
      />,
    );

    const textarea = screen.getByPlaceholderText("輸入場景描述...");
    fireEvent.change(textarea, { target: { value: "陰森的走廊與破窗" } });

    fireEvent.click(screen.getByRole("button", { name: "儲存" }));

    await waitFor(() => {
      expect(onSave).toHaveBeenCalledWith("廢棄醫院", {
        description: "陰森的走廊與破窗",
        imageBackend: null,
      });
    });
  });

  it("calls onGenerate when the generate button is clicked", () => {
    const onGenerate = vi.fn();
    renderSceneCard(
      <SceneCard
        name="廢棄醫院"
        scene={{ description: "陰森的走廊" }}
        projectName="demo"
        onSave={vi.fn()}
        onGenerate={onGenerate}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "生成場景" }));

    expect(onGenerate).toHaveBeenCalledWith("廢棄醫院");
  });

  it("calls onRename after editing the scene name", async () => {
    const onRename = vi.fn().mockResolvedValue(undefined);
    renderSceneCard(
      <SceneCard
        name="廢棄醫院"
        scene={{ description: "陰森的走廊" }}
        projectName="demo"
        onSave={vi.fn()}
        onRename={onRename}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "廢棄醫院" }));
    const input = screen.getByLabelText("場景名稱");
    fireEvent.change(input, { target: { value: "地下診所" } });
    fireEvent.keyDown(input, { key: "Enter" });

    await waitFor(() => {
      expect(onRename).toHaveBeenCalledWith("廢棄醫院", "地下診所");
    });
  });

  it("uploads a selected reference file immediately", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    const onUploadReference = vi.fn().mockResolvedValue(undefined);
    const { container } = renderSceneCard(
      <SceneCard
        name="廢棄醫院"
        scene={{ description: "陰森的走廊" }}
        projectName="demo"
        onSave={onSave}
        onUploadReference={onUploadReference}
      />,
    );

    const fileInput = container.querySelector("input[type='file']");
    expect(fileInput).not.toBeNull();

    const file = new File(["ref"], "scene.png", { type: "image/png" });
    fireEvent.change(fileInput as HTMLInputElement, {
      target: { files: [file] },
    });

    await waitFor(() => {
      expect(onUploadReference).toHaveBeenCalledWith("廢棄醫院", file);
      expect(screen.getByText("已上傳參考圖")).toBeInTheDocument();
    });
    expect(onSave).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "儲存" })).not.toBeInTheDocument();
  });

  it("confirms before deleting", async () => {
    const onDelete = vi.fn().mockResolvedValue(undefined);
    renderSceneCard(
      <SceneCard
        name="廢棄醫院"
        scene={{ description: "陰森的走廊" }}
        projectName="demo"
        onSave={vi.fn()}
        onDelete={onDelete}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: "刪除場景 廢棄醫院" }),
    );

    const confirmBtn = await screen.findByRole("button", { name: "確定" });
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(onDelete).toHaveBeenCalledWith("廢棄醫院");
    });
  });
});
