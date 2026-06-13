import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import { UI_LAYERS } from "@/utils/ui-layers";

export interface EntityMentionItem {
  name: string;
  kind: "character" | "clue" | "scene";
}

export interface EntityMentionMenuHandle {
  /** Returns true if the key was consumed (caller should preventDefault). */
  handleKeyDown: (key: string) => boolean;
}

interface EntityMentionMenuProps {
  readonly id?: string;
  readonly className?: string;
  readonly filter: string;
  readonly items: EntityMentionItem[];
  readonly onSelect: (item: EntityMentionItem) => void;
}

const DEFAULT_MENU_ID = "entity-mention-menu";
const WORKSPACE_POPOVER_Z_INDEX = Number(UI_LAYERS.workspacePopover.replace("z-", ""));

const KIND_LABELS: Record<EntityMentionItem["kind"], string> = {
  character: "角色",
  clue: "道具",
  scene: "場景",
};

const KIND_CLASSES: Record<EntityMentionItem["kind"], string> = {
  character: "text-cyan-300",
  clue: "text-yellow-400",
  scene: "text-emerald-300",
};

export const EntityMentionMenu = forwardRef<EntityMentionMenuHandle, EntityMentionMenuProps>(
  function EntityMentionMenu({ id = DEFAULT_MENU_ID, className = "", filter, items, onSelect }, ref) {
    const [activeIndex, setActiveIndex] = useState(0);
    const selectedOnMouseDownRef = useRef(false);

    const query = filter.toLowerCase();
    const filtered = items.filter((item) => item.name.toLowerCase().includes(query));

    useEffect(() => {
      setActiveIndex(0);
    }, [filter, filtered.length]);

    const itemRefs = useRef<Map<number, HTMLButtonElement>>(new Map());
    useEffect(() => {
      itemRefs.current.get(activeIndex)?.scrollIntoView?.({ block: "nearest" });
    }, [activeIndex]);

    useImperativeHandle(ref, () => ({
      handleKeyDown(key: string): boolean {
        if (key === "Escape") return true;
        if (filtered.length === 0) return false;
        switch (key) {
          case "ArrowDown":
            setActiveIndex((prev) => (prev + 1) % filtered.length);
            return true;
          case "ArrowUp":
            setActiveIndex((prev) => (prev - 1 + filtered.length) % filtered.length);
            return true;
          case "Enter":
          case "Tab": {
            const item = filtered[activeIndex];
            if (item) onSelect(item);
            return true;
          }
          default:
            return false;
        }
      },
    }), [activeIndex, filtered, onSelect]);

    if (filtered.length === 0) return null;

    return (
      <div
        id={id}
        role="listbox"
        aria-label="實體提及選單"
        className={`max-h-52 overflow-y-auto rounded-lg border border-gray-700 bg-gray-900 py-1 shadow-xl ${className}`}
        style={{ zIndex: WORKSPACE_POPOVER_Z_INDEX }}
      >
        {filtered.map((item, i) => {
          const isActive = i === activeIndex;
          return (
            <button
              key={`${item.kind}:${item.name}`}
              ref={(el) => {
                if (el) itemRefs.current.set(i, el);
                else itemRefs.current.delete(i);
              }}
              id={`${id}-option-${i}`}
              role="option"
              aria-selected={isActive}
              type="button"
              onMouseDown={(e) => {
                e.preventDefault();
                selectedOnMouseDownRef.current = true;
                onSelect(item);
              }}
              onClick={(e) => {
                e.preventDefault();
                if (selectedOnMouseDownRef.current) {
                  selectedOnMouseDownRef.current = false;
                  return;
                }
                onSelect(item);
              }}
              onMouseEnter={() => setActiveIndex(i)}
              className={`flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-sm transition-colors ${
                isActive ? "bg-gray-800" : "hover:bg-gray-800"
              }`}
            >
              <span className="min-w-0 truncate font-medium text-gray-300">{item.name}</span>
              <span className={`shrink-0 text-xs font-medium ${KIND_CLASSES[item.kind]}`}>
                {KIND_LABELS[item.kind]}
              </span>
            </button>
          );
        })}
      </div>
    );
  },
);
