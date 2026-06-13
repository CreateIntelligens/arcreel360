/**
 * entity-matching.ts — 實體名稱比對（前後端共用規格的 TypeScript 實作）
 *
 * 用途：在一段文字中掃描已知的角色 / 線索 / 場景名稱，回傳命中的原始 key。
 * 比對方式為 longest-first、非重疊的裸文掃描（不需要 @ 前綴）。
 *
 * 名稱來源為 project.json 的 characters / clues / scenes 的 key；
 * 若 key 形如「中文 (English)」會自動拆解為三個比對詞（完整 key、中文、英文）。
 */

export interface EntityMentionNames {
  characterNames: string[];
  clueNames: string[];
  sceneName: string | null;
}

export interface EntitySources {
  characters: Record<string, unknown>;
  clues: Record<string, unknown>;
  scenes?: Record<string, unknown>;
}

const ALIAS_PATTERN = /^(.+?)\s*[（(]\s*(.+?)\s*[）)]\s*$/;

export function expandEntityAliases(name: string): string[] {
  const trimmed = name.trim();
  if (!trimmed) return [];
  const m = ALIAS_PATTERN.exec(trimmed);
  if (!m) return [trimmed];
  const parts = [trimmed, m[1].trim(), m[2].trim()];
  const seen = new Set<string>();
  const result: string[] = [];
  for (const p of parts) {
    if (p && !seen.has(p)) { seen.add(p); result.push(p); }
  }
  return result;
}

export type EntityKind = "character" | "clue" | "scene";
const KIND_PRIORITY: Record<EntityKind, number> = { character: 0, clue: 1, scene: 2 };

interface AliasEntry {
  alias: string;
  originalKey: string;
  kind: EntityKind;
}

const ASCII_WORD_RE = /^[A-Za-z0-9_]+$/;
const ASCII_WORD_CHAR_RE = /[A-Za-z0-9_]/;

export function isAsciiWordName(name: string): boolean {
  return ASCII_WORD_RE.test(name);
}

export function isAsciiWordChar(char: string | undefined): boolean {
  return Boolean(char && ASCII_WORD_CHAR_RE.test(char));
}

// 以 code point 陣列（而非 UTF-16 code unit）做邊界檢查，與後端 Python 對齊。
function checkBoundary(cps: string[], start: number, length: number, alias: string): boolean {
  if (!isAsciiWordName(alias)) return true;
  if (start > 0 && isAsciiWordChar(cps[start - 1])) return false;
  const end = start + length;
  if (end < cps.length && isAsciiWordChar(cps[end])) return false;
  return true;
}

function buildEntries(names: Record<string, unknown> | undefined, kind: EntityKind): AliasEntry[] {
  if (!names) return [];
  const entries: AliasEntry[] = [];
  for (const key of Object.keys(names)) {
    for (const alias of expandEntityAliases(key)) {
      entries.push({ alias, originalKey: key, kind });
    }
  }
  return entries;
}

export function scanEntityMentions(text: string, entities: EntitySources): EntityMentionNames {
  const allEntries = [
    ...buildEntries(entities.characters, "character"),
    ...buildEntries(entities.clues, "clue"),
    ...buildEntries(entities.scenes, "scene"),
  ];

  const seenAliases = new Map<string, AliasEntry>();
  for (const entry of allEntries) {
    const existing = seenAliases.get(entry.alias);
    if (!existing || KIND_PRIORITY[entry.kind] < KIND_PRIORITY[existing.kind]) {
      seenAliases.set(entry.alias, entry);
    }
  }

  // 以 code point 為計量單位（與 Python str 索引一致），避免星平面字（emoji）
  // 在 UTF-16 下 length=2 導致前後端游標前進量不同而命中漂移。
  const textCps = Array.from(text);
  const sortedEntries = Array.from(seenAliases.values())
    .map((entry) => ({ ...entry, cps: Array.from(entry.alias) }))
    .sort((a, b) => {
      const d = b.cps.length - a.cps.length;
      return d !== 0 ? d : KIND_PRIORITY[a.kind] - KIND_PRIORITY[b.kind];
    });

  const foundChars = new Set<string>();
  const foundClues = new Set<string>();
  const foundScenes = new Set<string>();

  let i = 0;
  while (i < textCps.length) {
    let matched = false;
    for (const entry of sortedEntries) {
      const len = entry.cps.length;
      if (i + len > textCps.length) continue;
      let equal = true;
      for (let k = 0; k < len; k += 1) {
        if (textCps[i + k] !== entry.cps[k]) {
          equal = false;
          break;
        }
      }
      if (equal && checkBoundary(textCps, i, len, entry.alias)) {
        if (entry.kind === "character") foundChars.add(entry.originalKey);
        else if (entry.kind === "clue") foundClues.add(entry.originalKey);
        else foundScenes.add(entry.originalKey);
        i += len;
        matched = true;
        break;
      }
    }
    if (!matched) i += 1;
  }

  const sceneArr = Array.from(foundScenes).sort();
  return {
    characterNames: Array.from(foundChars).sort(),
    clueNames: Array.from(foundClues).sort(),
    sceneName: sceneArr[0] ?? null,
  };
}
