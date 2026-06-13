import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ConfirmProvider } from "@/components/ui/ConfirmProvider";
import { useConfirm } from "./useConfirm";

function TriggerButton({
  onResult,
  danger,
}: {
  onResult: (v: boolean) => void;
  danger?: boolean;
}) {
  const confirm = useConfirm();
  return (
    <button
      type="button"
      onClick={async () => {
        const ok = await confirm({ message: "要繼續嗎？", danger });
        onResult(ok);
      }}
    >
      開啟
    </button>
  );
}

describe("useConfirm", () => {
  it("resolves true when user confirms", async () => {
    const results: boolean[] = [];
    render(
      <ConfirmProvider>
        <TriggerButton onResult={(v) => results.push(v)} />
      </ConfirmProvider>,
    );

    fireEvent.click(screen.getByText("開啟"));
    expect(await screen.findByRole("alertdialog")).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "確定" }));
    });

    expect(results).toEqual([true]);
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  it("resolves false when user cancels", async () => {
    const results: boolean[] = [];
    render(
      <ConfirmProvider>
        <TriggerButton onResult={(v) => results.push(v)} />
      </ConfirmProvider>,
    );

    fireEvent.click(screen.getByText("開啟"));
    expect(await screen.findByRole("alertdialog")).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "取消" }));
    });

    expect(results).toEqual([false]);
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  it("resolves false on ESC", async () => {
    const results: boolean[] = [];
    render(
      <ConfirmProvider>
        <TriggerButton onResult={(v) => results.push(v)} />
      </ConfirmProvider>,
    );

    fireEvent.click(screen.getByText("開啟"));
    await screen.findByRole("alertdialog");

    await act(async () => {
      fireEvent.keyDown(window, { key: "Escape" });
    });

    expect(results).toEqual([false]);
  });

  it("throws when used outside ConfirmProvider", () => {
    function BareConsumer() {
      useConfirm();
      return null;
    }
    // 攔截 React error logging 避免污染輸出
    const spy = vi.fn();
    const originalError = console.error;
    console.error = spy;
    try {
      expect(() => render(<BareConsumer />)).toThrow(/ConfirmProvider/);
    } finally {
      console.error = originalError;
    }
  });
});
