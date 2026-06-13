import { createRef } from "react";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { EntityMentionMenu } from "./EntityMentionMenu";
import type { EntityMentionItem, EntityMentionMenuHandle } from "./EntityMentionMenu";

const ITEMS: EntityMentionItem[] = [
  { name: "錦衣衛", kind: "character" },
  { name: "青玉碎片", kind: "clue" },
];

describe("EntityMentionMenu", () => {
  const onSelect = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders items when items array is non-empty", () => {
    render(<EntityMentionMenu filter="" items={ITEMS} onSelect={onSelect} />);

    expect(screen.getByText("錦衣衛")).toBeInTheDocument();
    expect(screen.getByText("青玉碎片")).toBeInTheDocument();
    expect(screen.getByText("角色")).toBeInTheDocument();
    expect(screen.getByText("道具")).toBeInTheDocument();
  });

  it("returns null when items is empty", () => {
    const { container } = render(<EntityMentionMenu filter="" items={[]} onSelect={onSelect} />);

    expect(container.firstChild).toBeNull();
  });

  it("highlights first item by default", () => {
    render(<EntityMentionMenu filter="" items={ITEMS} onSelect={onSelect} />);

    expect(screen.getByText("錦衣衛").closest("button")).toHaveAttribute("aria-selected", "true");
  });

  it("cycles highlighted index with arrow keys", () => {
    const ref = createRef<EntityMentionMenuHandle>();
    render(<EntityMentionMenu ref={ref} filter="" items={ITEMS} onSelect={onSelect} />);

    act(() => {
      ref.current!.handleKeyDown("ArrowDown");
    });
    expect(screen.getByText("青玉碎片").closest("button")).toHaveAttribute("aria-selected", "true");

    act(() => {
      ref.current!.handleKeyDown("ArrowDown");
    });
    expect(screen.getByText("錦衣衛").closest("button")).toHaveAttribute("aria-selected", "true");

    act(() => {
      ref.current!.handleKeyDown("ArrowUp");
    });
    expect(screen.getByText("青玉碎片").closest("button")).toHaveAttribute("aria-selected", "true");
  });

  it("calls onSelect with highlighted item on Enter", () => {
    const ref = createRef<EntityMentionMenuHandle>();
    render(<EntityMentionMenu ref={ref} filter="" items={ITEMS} onSelect={onSelect} />);

    act(() => {
      ref.current!.handleKeyDown("ArrowDown");
    });
    act(() => {
      ref.current!.handleKeyDown("Enter");
    });

    expect(onSelect).toHaveBeenCalledWith(ITEMS[1]);
  });

  it("returns true for Escape", () => {
    const ref = createRef<EntityMentionMenuHandle>();
    render(<EntityMentionMenu ref={ref} filter="" items={ITEMS} onSelect={onSelect} />);

    let consumed = false;
    act(() => {
      consumed = ref.current!.handleKeyDown("Escape");
    });

    expect(consumed).toBe(true);
  });

  it("calls onSelect on mouse click", () => {
    render(<EntityMentionMenu filter="" items={ITEMS} onSelect={onSelect} />);

    fireEvent.click(screen.getByText("青玉碎片").closest("button")!);

    expect(onSelect).toHaveBeenCalledWith(ITEMS[1]);
  });
});
