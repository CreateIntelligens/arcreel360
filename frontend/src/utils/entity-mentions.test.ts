import { describe, expect, it } from "vitest";
import {
  buildEntityMentionUpdates,
  extractEntityMentions,
  stripKnownEntityMentionMarkers,
} from "@/utils/entity-mentions";

const entities = {
  characters: {
    Hero: {},
    "小明": {},
  },
  clues: {
    Key: {},
    "青玉碎片": {},
  },
  scenes: {
    古城: {},
  },
};

describe("entity mention helpers", () => {
  it("extracts known character and clue mentions from text", () => {
    expect(extractEntityMentions("@小明 拿起 @青玉碎片。@未知 不處理", entities)).toEqual({
      characterNames: ["小明"],
      clueNames: ["青玉碎片"],
      sceneName: null,
    });
  });

  it("extracts the first known scene mention as a scalar reference", () => {
    expect(extractEntityMentions("遠景 @古城，角色走入畫面", entities)).toEqual({
      characterNames: [],
      clueNames: [],
      sceneName: "古城",
    });
  });

  it("strips only known mention markers while preserving clean text", () => {
    expect(stripKnownEntityMentionMarkers("@Hero 看見 @Key，進入 @古城，@未知 保留。", entities)).toBe(
      "Hero 看見 Key，進入 古城，@未知 保留。",
    );
  });

  it("builds additive updates from nested prompt text", () => {
    expect(
      buildEntityMentionUpdates(
        { scene: "@Hero 靠近桌面", composition: { lighting: "@Key 旁的冷光" } },
        entities,
        { characterNames: ["小明"], clueNames: [], sceneName: "古城" },
      ),
    ).toEqual({
      characterNames: ["小明", "Hero"],
      clueNames: ["Key"],
      sceneName: "古城",
    });
  });
});
