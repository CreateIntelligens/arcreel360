import { useState, useEffect, useRef, useCallback } from "react";
import { useEntityMentionInput } from "../useEntityMentionInput";
import { EntityMentionMenu } from "../EntityMentionMenu";
import { MentionHighlightedText, MentionHighlightOverlay } from "../MentionHighlightOverlay";
import { stripKnownEntityMentionMarkers } from "@/utils/entity-mentions";
import type { DramaScene } from "@/types";
import { getSourceMentionValue, type SegmentMentionContext } from "./helpers";
import type { Segment, SegmentMentionDrafts, SegmentMentionDraftKey, SegmentUpdateExtras } from "./types";

interface TextColumnProps {
  segment: Segment;
  contentMode: "narration" | "drama";
  mentionContext: SegmentMentionContext;
  onMentionDraftChange: (key: SegmentMentionDraftKey, value: unknown) => void;
  buildMentionUpdatesForDraft: (
    patch: Partial<SegmentMentionDrafts>,
  ) => SegmentUpdateExtras | undefined;
  onUpdateNote?: (value: string) => void;
  onUpdateSourceText?: (value: string, extraUpdates?: SegmentUpdateExtras) => void;
}

export function TextColumn({
  segment,
  contentMode,
  mentionContext,
  onMentionDraftChange,
  buildMentionUpdatesForDraft,
  onUpdateNote,
  onUpdateSourceText,
}: TextColumnProps) {
  const noteValue = segment.note ?? "";
  const sourceFromSegment = getSourceMentionValue(segment, contentMode);
  const [noteDraft, setNoteDraft] = useState(noteValue);
  const committedRef = useRef(noteValue);
  const [sourceDraft, setSourceDraft] = useState(sourceFromSegment);
  const sourceCommittedRef = useRef(sourceFromSegment);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const updateSourceDraft = useCallback(
    (next: string) => {
      setSourceDraft(next);
      onMentionDraftChange("source", next);
    },
    [onMentionDraftChange],
  );
  const {
    menuOpen,
    filter,
    items,
    handleInputChange,
    handleKeyDown,
    handleBlur,
    selectItem,
    menuRef,
  } = useEntityMentionInput({
    value: sourceDraft,
    onChange: updateSourceDraft,
    entities: mentionContext.entities,
    textareaRef,
  });

  useEffect(() => {
    setNoteDraft(noteValue);
    committedRef.current = noteValue;
  }, [noteValue]);

  useEffect(() => {
    setSourceDraft(sourceFromSegment);
    sourceCommittedRef.current = sourceFromSegment;
  }, [sourceFromSegment]);

  const resizeTextarea = useCallback(() => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = `${el.scrollHeight}px`;
    }
  }, []);

  useEffect(() => {
    resizeTextarea();
  }, [sourceDraft, resizeTextarea]);

  const handleNoteBlur = () => {
    if (noteDraft !== committedRef.current) {
      committedRef.current = noteDraft;
      onUpdateNote?.(noteDraft);
    }
  };

  const handleSourceBlur = () => {
    const cleanSource = stripKnownEntityMentionMarkers(sourceDraft, mentionContext.entities);
    const extraUpdates = buildMentionUpdatesForDraft({ source: sourceDraft });

    if (cleanSource !== sourceDraft) {
      setSourceDraft(cleanSource);
      onMentionDraftChange("source", cleanSource);
    }

    if (cleanSource !== sourceCommittedRef.current || extraUpdates) {
      sourceCommittedRef.current = cleanSource;
      onUpdateSourceText?.(cleanSource, extraUpdates);
    }
  };

  const noteSection = (
    <div className="mt-auto pt-3 border-t border-gray-800">
      <span className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-2 block">
        備註
      </span>
      <textarea
        className="w-full resize-none rounded-lg border border-gray-700 bg-gray-800/50 px-3 py-2 text-sm text-gray-300 placeholder-gray-600 focus:border-indigo-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
        rows={4}
        placeholder="新增備註..."
        aria-label="備註"
        value={noteDraft}
        onChange={(e) => setNoteDraft(e.target.value)}
        onBlur={handleNoteBlur}
      />
    </div>
  );

  const sourceEditor = (
    <div className="relative rounded-lg border border-gray-800 bg-gray-900/30 hover:border-gray-700/60 focus-within:border-indigo-500/80 focus-within:bg-gray-800/20 transition-all duration-200">
      <MentionHighlightOverlay
        value={sourceDraft}
        entities={mentionContext.entities}
        linkedNames={mentionContext.currentNames}
        className="font-sans min-h-[8rem] px-3.5 py-3 text-sm leading-relaxed whitespace-pre-wrap break-words border border-transparent"
      />
      <textarea
        ref={textareaRef}
        className="font-sans relative min-h-[8rem] w-full resize-none overflow-hidden bg-transparent px-3.5 py-3 text-sm leading-relaxed placeholder-gray-600 border border-transparent focus:outline-none"
        style={{ color: "transparent", caretColor: "#d1d5db" }}
        value={sourceDraft}
        placeholder="（暫無原文）"
        aria-label="原文"
        aria-autocomplete="list"
        aria-controls="entity-mention-menu"
        role="combobox"
        aria-expanded={menuOpen}
        onChange={handleInputChange}
        onKeyDown={handleKeyDown}
        onBlur={() => {
          handleBlur();
          handleSourceBlur();
        }}
      />
      {menuOpen && (
        <EntityMentionMenu
          id="entity-mention-menu"
          ref={menuRef}
          filter={filter}
          items={items}
          onSelect={selectItem}
          className="absolute left-0 top-full mt-1 w-64"
        />
      )}
    </div>
  );

  if (contentMode === "narration") {
    return (
      <div className="flex h-full flex-col gap-1.5 p-3">
        <span className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-2">
          原文
        </span>
        {sourceEditor}
        {noteSection}
      </div>
    );
  }

  // Drama mode — 原文（場景描述）→ 旁白 → 對話
  const s = segment as DramaScene;
  const vp = s.video_prompt;
  const dialogue = (typeof vp === "object" && vp !== null && "dialogue" in vp)
    ? (vp.dialogue ?? [])
    : [];
  const narrationText = s.narration_text?.trim() ?? "";
  return (
    <div className="flex h-full flex-col gap-1.5 p-3 overflow-y-auto">
      <span className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-2">
        原文
      </span>
      {sourceEditor}
      <div className="mt-4 pt-3 border-t border-gray-800 flex flex-col gap-1.5">
        <span className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-2">
          旁白
        </span>
        {narrationText ? (
          <p className="text-sm leading-relaxed text-gray-300 whitespace-pre-wrap break-words">
            <MentionHighlightedText
              value={narrationText}
              entities={mentionContext.entities}
              linkedNames={mentionContext.currentNames}
            />
          </p>
        ) : (
          <p className="text-sm text-gray-500 italic">（暫無旁白）</p>
        )}
      </div>
      <div className="mt-4 pt-3 border-t border-gray-800 flex flex-col gap-1.5">
        <span className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-2">
          對話
        </span>
        {dialogue.length === 0 ? (
          <p className="text-sm text-gray-500 italic">（暫無對話）</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {dialogue.map((d: { speaker: string; line: string }, i: number) => (
              <li key={i} className="text-sm text-gray-300">
                <span className="font-bold text-indigo-400">{d.speaker}</span>
                <span className="mx-1 text-gray-600">:</span>
                <span>
                  <MentionHighlightedText
                    value={d.line}
                    entities={mentionContext.entities}
                    linkedNames={mentionContext.currentNames}
                  />
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
      {noteSection}
    </div>
  );
}
