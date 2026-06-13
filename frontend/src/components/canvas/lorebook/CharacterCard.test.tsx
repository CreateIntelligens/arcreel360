import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ConfirmProvider } from "@/components/ui/ConfirmProvider";
import { CharacterCard } from "./CharacterCard";
import { useAppStore } from "@/stores/app-store";

vi.mock("@/components/canvas/timeline/VersionTimeMachine", () => ({
  VersionTimeMachine: () => <div data-testid="version-time-machine">versions</div>,
}));

function renderCharacterCard(ui: ReactElement) {
  return render(ui, { wrapper: ConfirmProvider });
}

describe("CharacterCard", () => {
  beforeEach(() => {
    useAppStore.setState(useAppStore.getInitialState(), true);
    vi.restoreAllMocks();
    Object.defineProperty(globalThis.URL, "createObjectURL", {
      writable: true,
      value: vi.fn(() => "blob:character-ref"),
    });
    Object.defineProperty(globalThis.URL, "revokeObjectURL", {
      writable: true,
      value: vi.fn(),
    });
  });

  it("renders existing saved reference image", () => {
    renderCharacterCard(
      <CharacterCard
        name="Hero"
        character={{
          description: "hero desc",
          voice_style: "warm",
          reference_image: "characters/refs/Hero.png",
        }}
        projectName="demo"
        onSave={vi.fn()}
        onUploadReference={vi.fn()}
        onGenerate={vi.fn()}
      />,
    );

    expect(screen.getByAltText("Hero 參考圖")).toHaveAttribute(
      "src",
      "/api/v1/files/demo/characters/refs/Hero.png",
    );
  });

  it("uploads a selected reference file immediately", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    const onUploadReference = vi.fn().mockResolvedValue(undefined);
    const { container } = renderCharacterCard(
      <CharacterCard
        name="Hero"
        character={{ description: "hero desc", voice_style: "warm" }}
        projectName="demo"
        onSave={onSave}
        onUploadReference={onUploadReference}
        onGenerate={vi.fn()}
      />,
    );

    const fileInput = container.querySelector("input[type='file']");
    expect(fileInput).not.toBeNull();

    const file = new File(["ref"], "hero.png", { type: "image/png" });
    fireEvent.change(fileInput as HTMLInputElement, { target: { files: [file] } });

    await waitFor(() => {
      expect(onUploadReference).toHaveBeenCalledWith("Hero", file);
      expect(screen.getByText("已上傳參考圖")).toBeInTheDocument();
    });
    expect(onSave).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "儲存" })).not.toBeInTheDocument();
  });
});
