import { useCallback, useEffect, useRef } from "react";
import type { ChangeEvent } from "react";
import { EntityMentionMenu } from "@/components/canvas/timeline/EntityMentionMenu";
import { MentionHighlightOverlay } from "@/components/canvas/timeline/MentionHighlightOverlay";
import { useEntityMentionInput } from "@/components/canvas/timeline/useEntityMentionInput";
import type { EntityMentionNames, EntityMentionSources } from "@/utils/entity-mentions";
import { UI_LAYERS } from "@/utils/ui-layers";

interface AutoTextareaProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
  /** 提供時啟用 @ 角色/道具/場景自動補完選單與高亮。 */
  entities?: EntityMentionSources;
  /** 該片段已關聯的實體名稱；裸名（無 @）也會高亮，與原文一致。
   *  僅在同時提供 `entities`（啟用高亮層）時生效。 */
  linkedNames?: EntityMentionNames;
}

const EMPTY_MENTION_ENTITIES: EntityMentionSources = {
  characters: {},
  clues: {},
  scenes: {},
};

// Overlay 與 textarea 必須共用 metrics, 否則高亮文字會對不齊。
const SHARED_METRICS = "px-2.5 py-2 font-mono text-xs leading-4 tracking-normal whitespace-pre-wrap break-words";
const TEXTAREA_BASE = `w-full resize-none overflow-y-auto rounded-lg border ${SHARED_METRICS}`;
const TEXTAREA_CHROME = "border-gray-700 bg-gray-800 placeholder-gray-500 focus:border-indigo-500 focus:outline-none";

/** Auto-resizing textarea that grows with its content.
 *  Optionally supports `@` entity mention menu when `entities` is provided. */
export function AutoTextarea({
  value,
  onChange,
  placeholder,
  className,
  entities,
  linkedNames,
}: AutoTextareaProps) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const overlayRef = useRef<HTMLPreElement>(null);

  const handleScroll = (e: React.UIEvent<HTMLTextAreaElement>) => {
    if (overlayRef.current) {
      overlayRef.current.scrollTop = e.currentTarget.scrollTop;
    }
  };

  const resize = useCallback(() => {
    const el = ref.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = `${el.scrollHeight}px`;
    }
  }, []);

  useEffect(() => {
    resize();
  }, [value, resize]);

  const mentionEntities = entities ?? EMPTY_MENTION_ENTITIES;
  const mentionEnabled = Boolean(entities);
  const mention = useEntityMentionInput({
    value,
    onChange,
    entities: mentionEntities,
    textareaRef: ref,
  });
  const textareaClassName = `${TEXTAREA_BASE} ${TEXTAREA_CHROME}`;

  const handleChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    if (mentionEnabled) {
      mention.handleInputChange(e);
      return;
    }
    onChange(e.target.value);
  };

  const classes = (className ?? "").split(/\s+/).filter(Boolean);
  const heightAndScrollClasses = classes.filter(c =>
    c.startsWith("max-h-") ||
    c.startsWith("h-") ||
    c.startsWith("overflow-") ||
    c === "scrollbar-thin"
  );
  const containerClasses = classes.filter(c =>
    !c.startsWith("max-h-") &&
    !c.startsWith("h-") &&
    !c.startsWith("overflow-") &&
    c !== "scrollbar-thin"
  );

  const containerClassName = containerClasses.join(" ");
  const textSpecificClassName = heightAndScrollClasses.join(" ");

  if (!mentionEnabled) {
    return (
      <textarea
        ref={ref}
        value={value}
        onChange={handleChange}
        onInput={resize}
        onScroll={handleScroll}
        placeholder={placeholder}
        rows={2}
        className={`${textareaClassName} text-gray-200 ${className ?? ""}`}
      />
    );
  }

  return (
    <div className={`relative ${containerClassName}`}>
      <MentionHighlightOverlay
        ref={overlayRef}
        value={value}
        entities={mentionEntities}
        linkedNames={linkedNames}
        className={`${SHARED_METRICS} border border-transparent text-gray-200 ${textSpecificClassName}`}
      />
      <textarea
        ref={ref}
        value={value}
        onChange={handleChange}
        onInput={resize}
        onScroll={handleScroll}
        onKeyDown={mention.handleKeyDown}
        onBlur={mention.handleBlur}
        placeholder={placeholder}
        rows={2}
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={mention.menuOpen}
        aria-controls={mention.menuOpen ? "entity-mention-menu" : undefined}
        style={{ color: "transparent", caretColor: "#e5e7eb", background: "transparent" }}
        className={`relative ${textareaClassName} ${textSpecificClassName}`}
      />
      {mention.menuOpen && (
        <EntityMentionMenu
          ref={mention.menuRef}
          filter={mention.filter}
          items={mention.items}
          onSelect={mention.selectItem}
          className={`absolute left-0 top-full mt-1 w-full ${UI_LAYERS.workspacePopover}`}
        />
      )}
    </div>
  );
}
