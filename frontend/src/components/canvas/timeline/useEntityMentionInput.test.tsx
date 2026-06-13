import { useRef, useState } from "react";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { extractEntityMentions } from "@/utils/entity-mentions";
import { useEntityMentionInput } from "./useEntityMentionInput";
import type { EntityMentionItem } from "./EntityMentionMenu";

const entities = {
  characters: {
    "錦衣衛": {},
    小明: {},
  },
  clues: {
    青玉碎片: {},
  },
  scenes: {
    古城: {},
  },
};

type HookValue = ReturnType<typeof useEntityMentionInput> & {
  value: string;
};

let latest: HookValue | null = null;

function HookHarness({ initialValue = "" }: { initialValue?: string }) {
  const [value, setValue] = useState(initialValue);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const hook = useEntityMentionInput({
    value,
    onChange: setValue,
    entities,
    textareaRef,
  });

  latest = {
    ...hook,
    value,
  };

  return (
    <textarea
      data-testid="entity-input"
      ref={textareaRef}
      value={value}
      onChange={hook.handleInputChange}
      onKeyDown={hook.handleKeyDown}
    />
  );
}

function inputElement(): HTMLTextAreaElement {
  return screen.getByTestId("entity-input") as HTMLTextAreaElement;
}

function changeInput(value: string, cursor = value.length): void {
  fireEvent.change(inputElement(), {
    target: {
      value,
      selectionStart: cursor,
    },
  });
}

describe("useEntityMentionInput", () => {
  beforeEach(() => {
    latest = null;
    vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => {
      cb(0);
      return 1;
    });
  });

  it("opens the menu for a boundary @ at the end", () => {
    render(<HookHarness />);

    changeInput("abc @");

    expect(latest!.menuOpen).toBe(true);
    expect(latest!.filter).toBe("");
  });

  it("updates filter from text between @ and cursor", () => {
    render(<HookHarness />);

    changeInput("@錦");

    expect(latest!.menuOpen).toBe(true);
    expect(latest!.filter).toBe("錦");
  });

  it("does not open without a boundary before @", () => {
    render(<HookHarness />);

    changeInput("abc@");

    expect(latest!.menuOpen).toBe(false);
  });

  it("closes when whitespace appears after the token", () => {
    render(<HookHarness />);

    changeInput("@a");
    expect(latest!.menuOpen).toBe(true);

    changeInput("@a b");

    expect(latest!.menuOpen).toBe(false);
  });

  it("inserts the selected item and moves cursor after the trailing space", () => {
    render(<HookHarness />);
    changeInput("@錦");

    const item: EntityMentionItem = { name: "錦衣衛", kind: "character" };
    act(() => {
      latest!.selectItem(item);
    });

    expect(latest!.value).toBe("@錦衣衛 ");
    expect(inputElement().selectionStart).toBe(1 + item.name.length + 1);
  });

  it("does not overwrite or clear subsequent characters when inserting mention at the beginning", () => {
    render(<HookHarness initialValue="原本有一些文字" />);
    changeInput("@錦原本有一些文字", 2);

    const item: EntityMentionItem = { name: "錦衣衛", kind: "character" };
    act(() => {
      latest!.selectItem(item);
    });

    expect(latest!.value).toBe("@錦衣衛 原本有一些文字");
  });

  it("offers scene mentions in the same menu", () => {
    render(<HookHarness />);

    changeInput("@古");

    expect(latest!.items).toContainEqual({ name: "古城", kind: "scene" });
  });

  it("produces text recognised by extractEntityMentions", () => {
    render(<HookHarness />);
    changeInput("@錦");

    act(() => {
      latest!.selectItem({ name: "錦衣衛", kind: "character" });
    });

    expect(extractEntityMentions(latest!.value, entities)).toEqual({
      characterNames: ["錦衣衛"],
      clueNames: [],
      sceneName: null,
    });
  });
});
