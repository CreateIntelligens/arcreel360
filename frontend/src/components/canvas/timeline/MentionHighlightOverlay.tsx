import { forwardRef, useMemo } from "react";
import type { EntityMentionNames, EntityMentionSources } from "@/utils/entity-mentions";
import {
  tokenizeForHighlight,
  type EntityMentionKind,
  type MentionToken,
} from "@/utils/entity-mentions-highlight";

interface MentionHighlightOverlayProps {
  value: string;
  entities: EntityMentionSources;
  linkedNames?: EntityMentionNames;
  /** 應與外層 textarea 完全一致的 padding / font / line-height / letter-spacing 等 className。 */
  className?: string;
}

interface MentionHighlightedTextProps {
  value: string;
  entities: EntityMentionSources;
  linkedNames?: EntityMentionNames;
}

type MentionHighlightContentProps = MentionHighlightedTextProps;

const MENTION_HIGHLIGHT_CLASSES: Record<EntityMentionKind, string> = {
  character: "bg-cyan-400/15 text-cyan-300 rounded px-0.5 box-decoration-clone",
  clue: "bg-yellow-400/15 text-yellow-300 rounded px-0.5 box-decoration-clone",
  scene: "bg-emerald-400/15 text-emerald-300 rounded px-0.5 box-decoration-clone",
};

function renderMentionTokens(tokens: MentionToken[]) {
  return tokens.map((token, index) => {
    if (token.type === "text") {
      return <span key={index}>{token.value}</span>;
    }

    return (
      <span key={index} className={MENTION_HIGHLIGHT_CLASSES[token.kind]}>
        {token.value}
      </span>
    );
  });
}

function useMentionHighlightTokens(
  value: string,
  entities: EntityMentionSources,
  linkedNames?: EntityMentionNames,
) {
  return useMemo(
    () => tokenizeForHighlight(value, entities, { linkedNames }),
    [value, entities, linkedNames],
  );
}

function MentionHighlightContent({
  value,
  entities,
  linkedNames,
}: MentionHighlightContentProps) {
  const tokens = useMentionHighlightTokens(value, entities, linkedNames);

  return <>{renderMentionTokens(tokens)}</>;
}

/**
 * 後置疊在 textarea 後面、用來把已知 @角色/道具/場景 高亮顯示的 mirror 層。
 *
 * 使用方:
 * - 用 `<div class="relative">` 同時包住 textarea 與本元件
 * - textarea 設 `color: transparent; caret-color: currentColor`
 * - 本元件設 `absolute inset-0 pointer-events-none` 並複製 textarea 的 metric class
 */
export const MentionHighlightOverlay = forwardRef<HTMLPreElement, MentionHighlightOverlayProps>(
  function MentionHighlightOverlay({ value, entities, linkedNames, className = "" }, ref) {
    return (
      <pre
        ref={ref}
        aria-hidden="true"
        data-testid="mention-highlight-overlay"
        className={`pointer-events-none select-none absolute inset-0 m-0 overflow-hidden whitespace-pre-wrap break-words ${className}`}
      >
        <MentionHighlightContent
          value={value}
          entities={entities}
          linkedNames={linkedNames}
        />
        {/* 結尾若是換行,加一個 zero-width space 讓最後一行高度被計算到,避免捲動位移 */}
        {value.endsWith("\n") && "​"}
      </pre>
    );
  },
);

export function MentionHighlightedText({
  value,
  entities,
  linkedNames,
}: MentionHighlightedTextProps) {
  return (
    <MentionHighlightContent
      value={value}
      entities={entities}
      linkedNames={linkedNames}
    />
  );
}
