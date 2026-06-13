import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ConfirmProvider } from "@/components/ui/ConfirmProvider";
import { LorebookReferenceImageField } from "./LorebookReferenceImageField";

function renderReferenceField({
  onUpload = vi.fn(),
  onRemove = vi.fn(),
}: {
  onUpload?: (file: File) => Promise<void> | void;
  onRemove?: () => Promise<void> | void;
} = {}) {
  return render(
    <ConfirmProvider>
      <LorebookReferenceImageField
        name="Hero"
        savedUrl="/hero.png"
        onUpload={onUpload}
        onRemove={onRemove}
      />
    </ConfirmProvider>,
  );
}

describe("LorebookReferenceImageField", () => {
  it("uses one replace action and confirms removal from the image corner", async () => {
    const onRemove = vi.fn().mockResolvedValue(undefined);
    renderReferenceField({ onRemove });

    expect(screen.getByRole("button", { name: "替換參考圖" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "更換" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "移除 Hero 參考圖" }));

    expect(onRemove).not.toHaveBeenCalled();
    expect(screen.getByRole("alertdialog")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "移除" }));

    await waitFor(() => {
      expect(onRemove).toHaveBeenCalledTimes(1);
    });
  });
});
