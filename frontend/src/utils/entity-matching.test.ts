import { describe, expect, it } from "vitest";
import { expandEntityAliases, scanEntityMentions } from "@/utils/entity-matching";

// ============ expandEntityAliases ============

describe("expandEntityAliases", () => {
  it("returns plain Chinese name as-is", () => {
    expect(expandEntityAliases("錦衣衛")).toEqual(["錦衣衛"]);
  });

  it("returns plain English name as-is", () => {
    expect(expandEntityAliases("Hero")).toEqual(["Hero"]);
  });

  it("splits half-width parentheses: 阿克 (Arke)", () => {
    expect(expandEntityAliases("阿克 (Arke)")).toEqual(["阿克 (Arke)", "阿克", "Arke"]);
  });

  it("splits full-width parentheses: 青玉碎片（Jade Shard）", () => {
    expect(expandEntityAliases("青玉碎片（Jade Shard）")).toEqual([
      "青玉碎片（Jade Shard）", "青玉碎片", "Jade Shard",
    ]);
  });

  it("trims outer whitespace", () => {
    expect(expandEntityAliases("  阿克  (  Arke  )  ")).toEqual([
      "阿克  (  Arke  )", "阿克", "Arke",
    ]);
  });

  it("returns empty array for empty string", () => {
    expect(expandEntityAliases("")).toEqual([]);
  });

  it("deduplicates when parts are identical", () => {
    expect(expandEntityAliases("Foo (Foo)")).toEqual(["Foo (Foo)", "Foo"]);
  });
});

// ============ scanEntityMentions ============

const CHARACTERS: Record<string, unknown> = {
  "阿克 (Arke)": {},
  "錦衣衛": {},
  "小明": {},
};

const CLUES: Record<string, unknown> = {
  "青玉碎片（Jade Shard）": {},
  Key: {},
};

const SCENES: Record<string, unknown> = {
  "古城": {},
  "荒野 (Wasteland)": {},
};

const entities = { characters: CHARACTERS, clues: CLUES, scenes: SCENES };

describe("scanEntityMentions", () => {
  it("matches basic Chinese names", () => {
    expect(scanEntityMentions("小明拿起了青玉碎片", entities)).toEqual({
      characterNames: ["小明"],
      clueNames: ["青玉碎片（Jade Shard）"],
      sceneName: null,
    });
  });

  it("matches English aliases and maps back to original key", () => {
    expect(scanEntityMentions("Arke found the Jade Shard", entities)).toEqual({
      characterNames: ["阿克 (Arke)"],
      clueNames: ["青玉碎片（Jade Shard）"],
      sceneName: null,
    });
  });

  it("matches the full key including parentheses", () => {
    const result = scanEntityMentions("角色阿克 (Arke)出場了", entities);
    expect(result.characterNames).toContain("阿克 (Arke)");
  });

  it("prefers longest match first", () => {
    const chars = { "錦衣衛": {}, "錦衣": {} };
    const result = scanEntityMentions("錦衣衛出場", { characters: chars, clues: {}, scenes: {} });
    expect(result.characterNames).toEqual(["錦衣衛"]);
  });

  it("does not overlap matches", () => {
    const chars = { "甲乙": {}, "乙丙": {} };
    const result = scanEntityMentions("甲乙丙", { characters: chars, clues: {} });
    // "甲乙" 先命中，游標跳到 "丙"，"乙丙" 不會命中
    expect(result.characterNames).toEqual(["甲乙"]);
  });

  it("returns scene_name from sorted first match", () => {
    const result = scanEntityMentions("古城和荒野都很美", entities);
    expect(result.sceneName).not.toBeNull();
  });

  it("matches scene English alias", () => {
    const result = scanEntityMentions("the Wasteland is vast", entities);
    expect(result.sceneName).toBe("荒野 (Wasteland)");
  });

  it("character wins over clue for same-name cross-group conflict", () => {
    const result = scanEntityMentions("古玉很重要", {
      characters: { "古玉": {} },
      clues: { "古玉": {} },
    });
    expect(result.characterNames).toEqual(["古玉"]);
    expect(result.clueNames).toEqual([]);
  });

  it("respects ASCII word boundary — no match inside longer word", () => {
    const result = scanEntityMentions("Heroic action by Hero", {
      characters: { Hero: {} }, clues: {},
    });
    expect(result.characterNames).toEqual(["Hero"]);
  });

  it("respects ASCII word boundary — no match with word-char prefix", () => {
    const result = scanEntityMentions("MonKey business", {
      characters: {}, clues: { Key: {} },
    });
    expect(result.clueNames).toEqual([]);
  });

  it("returns empty for unknown text", () => {
    expect(scanEntityMentions("未知角色出場", entities)).toEqual({
      characterNames: [], clueNames: [], sceneName: null,
    });
  });

  it("returns empty for empty text", () => {
    expect(scanEntityMentions("", entities)).toEqual({
      characterNames: [], clueNames: [], sceneName: null,
    });
  });

  it("returns empty for empty entities", () => {
    expect(scanEntityMentions("一些文字", { characters: {}, clues: {} })).toEqual({
      characterNames: [], clueNames: [], sceneName: null,
    });
  });

  it("finds multiple characters and scene in one text", () => {
    const result = scanEntityMentions("小明和錦衣衛在古城相遇", entities);
    expect(result.characterNames.sort()).toEqual(["小明", "錦衣衛"]);
    expect(result.sceneName).toBe("古城");
  });

  it("alias results use original key, not the alias itself", () => {
    const result = scanEntityMentions("Arke 和 Jade Shard", entities);
    expect(result.characterNames).toContain("阿克 (Arke)");
    expect(result.clueNames).toContain("青玉碎片（Jade Shard）");
    expect(result.characterNames).not.toContain("Arke");
    expect(result.clueNames).not.toContain("Jade Shard");
  });
});
