import { useCallback, useMemo, useRef, useState } from "react";
import type { ChangeEvent, KeyboardEvent, RefObject } from "react";
import type { EntityMentionItem, EntityMentionMenuHandle } from "./EntityMentionMenu";
import type { EntityMentionSources } from "@/utils/entity-mentions";

export type { EntityMentionSources };

export function useEntityMentionInput(opts: {
  value: string;
  onChange: (next: string) => void;
  entities: EntityMentionSources;
  textareaRef: RefObject<HTMLTextAreaElement | null>;
}): {
  menuOpen: boolean;
  filter: string;
  items: EntityMentionItem[];
  handleInputChange: (e: ChangeEvent<HTMLTextAreaElement>) => void;
  handleKeyDown: (e: KeyboardEvent<HTMLTextAreaElement>) => void;
  handleBlur: () => void;
  selectItem: (item: EntityMentionItem) => void;
  menuRef: RefObject<EntityMentionMenuHandle | null>;
} {
  const { value, onChange, entities, textareaRef } = opts;
  const [menuOpen, setMenuOpen] = useState(false);
  const [filter, setFilter] = useState("");
  const atPosRef = useRef(-1);
  const menuRef = useRef<EntityMentionMenuHandle | null>(null);

  const allItems = useMemo<EntityMentionItem[]>(() => [
    ...Object.keys(entities.characters)
      .filter(Boolean)
      .map((name) => ({ name, kind: "character" as const })),
    ...Object.keys(entities.clues)
      .filter(Boolean)
      .map((name) => ({ name, kind: "clue" as const })),
    ...Object.keys(entities.scenes ?? {})
      .filter(Boolean)
      .map((name) => ({ name, kind: "scene" as const })),
  ], [entities.characters, entities.clues, entities.scenes]);

  const items = useMemo(() => {
    const query = filter.toLowerCase();
    return allItems.filter((item) => item.name.toLowerCase().includes(query));
  }, [allItems, filter]);

  const closeMenu = useCallback(() => {
    setMenuOpen(false);
    setFilter("");
    atPosRef.current = -1;
  }, []);

  const detectMention = useCallback((nextValue: string, cursor: number) => {
    const textBeforeCursor = nextValue.slice(0, cursor);
    const lastAt = textBeforeCursor.lastIndexOf("@");

    if (lastAt < 0) {
      closeMenu();
      return;
    }

    const charBefore = lastAt > 0 ? textBeforeCursor[lastAt - 1] : undefined;
    const atBoundary = charBefore === undefined || /\s/.test(charBefore);
    const afterAt = textBeforeCursor.slice(lastAt + 1);
    const noWhitespaceAfterAt = !/\s/.test(afterAt);

    if (atBoundary && noWhitespaceAfterAt) {
      setMenuOpen(true);
      setFilter(afterAt);
      atPosRef.current = lastAt;
      return;
    }

    closeMenu();
  }, [closeMenu]);

  const handleInputChange = useCallback((e: ChangeEvent<HTMLTextAreaElement>) => {
    const nextValue = e.target.value;
    const cursor = e.target.selectionStart ?? nextValue.length;
    onChange(nextValue);
    detectMention(nextValue, cursor);
  }, [detectMention, onChange]);

  const handleKeyDown = useCallback((e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (!menuOpen) return;

    const consumed = menuRef.current?.handleKeyDown(e.key) ?? e.key === "Escape";
    if (!consumed) return;

    e.preventDefault();
    if (e.key === "Escape") {
      closeMenu();
    }
  }, [closeMenu, menuOpen]);

  const selectItem = useCallback((item: EntityMentionItem) => {
    const atPos = atPosRef.current;
    if (atPos < 0) return;

    const before = value.slice(0, atPos);
    const after = value.slice(atPos + 1 + filter.length);
    const next = `${before}@${item.name} ${after.trimStart()}`;
    const cursor = before.length + 1 + item.name.length + 1;

    onChange(next);
    closeMenu();

    const moveCursor = () => {
      const textarea = textareaRef.current;
      if (!textarea) return;
      textarea.focus();
      textarea.setSelectionRange(cursor, cursor);
    };

    if (typeof requestAnimationFrame === "function") {
      requestAnimationFrame(moveCursor);
    } else {
      moveCursor();
    }
  }, [closeMenu, filter, onChange, textareaRef, value]);

  const handleBlur = useCallback(() => {
    // 失焦延遲關閉, 避免 mousedown 選項時就立刻關掉。
    setTimeout(closeMenu, 0);
  }, [closeMenu]);

  return {
    menuOpen,
    filter,
    items,
    handleInputChange,
    handleKeyDown,
    handleBlur,
    selectItem,
    menuRef,
  };
}
