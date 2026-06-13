import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AutoTextarea } from "@/components/ui/AutoTextarea";

const entities = {
  characters: {
    "錦衣衛": {},
  },
  clues: {},
};

describe("AutoTextarea", () => {
  it("renders highlight spans for complete known mentions only", () => {
    const { rerender } = render(
      <AutoTextarea
        value="@錦衣衛"
        onChange={vi.fn()}
        entities={entities}
      />,
    );

    const overlay = screen.getByTestId("mention-highlight-overlay");
    expect(within(overlay).getByText("@錦衣衛")).toHaveClass("text-cyan-300");

    rerender(
      <AutoTextarea
        value="@錦衣"
        onChange={vi.fn()}
        entities={entities}
      />,
    );

    const partialOverlay = screen.getByTestId("mention-highlight-overlay");
    expect(within(partialOverlay).getByText("@錦衣")).not.toHaveClass("text-cyan-300");
  });

  it("renders highlight overlay synced with textarea content", () => {
    render(
      <AutoTextarea
        value="@錦衣衛 戰鬥場景"
        onChange={vi.fn()}
        entities={entities}
      />,
    );

    const overlay = screen.getByTestId("mention-highlight-overlay");
    expect(within(overlay).getByText("@錦衣衛")).toHaveClass("text-cyan-300");
    expect(overlay).toHaveTextContent("@錦衣衛 戰鬥場景");
  });

  it("keeps the highlight mirror out of user selection to avoid copied duplicates", () => {
    render(
      <AutoTextarea
        value="@錦衣衛 戰鬥場景"
        onChange={vi.fn()}
        entities={entities}
      />,
    );

    expect(screen.getByTestId("mention-highlight-overlay")).toHaveClass("select-none");
  });
});
