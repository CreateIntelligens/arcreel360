import type { EntityMentionNames, EntityMentionSources } from "@/utils/entity-mentions";
import {
  expandEntityAliases,
  isAsciiWordChar,
  isAsciiWordName,
  type EntityKind,
} from "@/utils/entity-matching";

export type EntityMentionKind = EntityKind;

export type MentionToken =
  | { type: "text"; value: string }
  | { type: "mention"; value: string; name: string; kind: EntityMentionKind };

interface MentionCandidate {
  // name：原始實體 key（token 語意用，對應 project.json）
  name: string;
  // alias：實際比對與畫面顯示用的文字（裸名路徑可能是別名，如「阿克」）
  alias: string;
  kind: EntityMentionKind;
}

interface HighlightOptions {
  linkedNames?: EntityMentionNames;
}

function sortCandidates(candidates: MentionCandidate[]): MentionCandidate[] {
  return candidates
    .filter((candidate) => Boolean(candidate.alias))
    .sort((a, b) => b.alias.length - a.alias.length);
}

// @ 路徑：沿用原 key 比對（使用者手打 @ 為既有行為，不展開別名）
function sortedCandidates(entities: EntityMentionSources): MentionCandidate[] {
  return sortCandidates([
    ...Object.keys(entities.characters)
      .map((name) => ({ name, alias: name, kind: "character" as const })),
    ...Object.keys(entities.clues)
      .map((name) => ({ name, alias: name, kind: "clue" as const })),
    ...Object.keys(entities.scenes ?? {})
      .map((name) => ({ name, alias: name, kind: "scene" as const })),
  ]);
}

// 裸名路徑：展開別名（「阿克 (Arke)」→ 阿克 / Arke / 完整 key），
// 比對與顯示用 alias，token.name 仍指回原 key。與後端 entity-matching 規格一致。
function expandLinked(name: string, kind: EntityMentionKind): MentionCandidate[] {
  return expandEntityAliases(name).map((alias) => ({ name, alias, kind }));
}

function sortedLinkedCandidates(linkedNames?: EntityMentionNames): MentionCandidate[] {
  if (!linkedNames) return [];

  return sortCandidates([
    ...linkedNames.characterNames.flatMap((name) => expandLinked(name, "character")),
    ...linkedNames.clueNames.flatMap((name) => expandLinked(name, "clue")),
    ...(linkedNames.sceneName ? expandLinked(linkedNames.sceneName, "scene") : []),
  ]);
}

function isMentionStart(text: string, index: number): boolean {
  if (text[index] !== "@") return false;
  if (index === 0) return true;
  return /\s/.test(text[index - 1]);
}

function isMentionBoundary(char: string | undefined): boolean {
  if (char === undefined) return true;
  if (/\s/.test(char)) return true;
  return !/[\p{L}\p{N}_]/u.test(char);
}

function isPlainMentionBoundary(text: string, start: number, name: string): boolean {
  if (text[start - 1] === "@") return false;
  if (!isAsciiWordName(name)) return true;
  return !isAsciiWordChar(text[start - 1]) && !isAsciiWordChar(text[start + name.length]);
}

function findMentionAt(
  text: string,
  start: number,
  candidates: MentionCandidate[],
): MentionCandidate | null {
  return candidates.find((candidate) => {
    if (!text.startsWith(candidate.alias, start)) {
      return false;
    }

    return isMentionBoundary(text[start + candidate.alias.length]);
  }) ?? null;
}

function findPlainMentionAt(
  text: string,
  start: number,
  candidates: MentionCandidate[],
): MentionCandidate | null {
  return candidates.find((candidate) =>
    text.startsWith(candidate.alias, start) &&
    isPlainMentionBoundary(text, start, candidate.alias)
  ) ?? null;
}

function appendText(tokens: MentionToken[], value: string): void {
  if (!value) return;

  const previous = tokens[tokens.length - 1];
  if (previous?.type === "text") {
    previous.value += value;
    return;
  }

  tokens.push({ type: "text", value });
}

function appendMentionToken(
  tokens: MentionToken[],
  mention: MentionCandidate,
  value: string,
): void {
  tokens.push({
    type: "mention",
    value,
    name: mention.name,
    kind: mention.kind,
  });
}

export function tokenizeForHighlight(
  text: string,
  entities: EntityMentionSources,
  options: HighlightOptions = {},
): MentionToken[] {
  const candidates = sortedCandidates(entities);
  const linkedCandidates = sortedLinkedCandidates(options.linkedNames);
  const tokens: MentionToken[] = [];
  let textStart = 0;

  for (let index = 0; index < text.length; index += 1) {
    if (isMentionStart(text, index)) {
      const mention = findMentionAt(text, index + 1, candidates);
      if (!mention) {
        continue;
      }

      appendText(tokens, text.slice(textStart, index));
      appendMentionToken(tokens, mention, `@${mention.alias}`);
      index += mention.alias.length;
      textStart = index + 1;
      continue;
    }

    const plainMention = findPlainMentionAt(text, index, linkedCandidates);
    if (!plainMention) {
      continue;
    }

    appendText(tokens, text.slice(textStart, index));
    appendMentionToken(tokens, plainMention, plainMention.alias);
    index += plainMention.alias.length - 1;
    textStart = index + 1;
  }

  appendText(tokens, text.slice(textStart));
  return tokens;
}
