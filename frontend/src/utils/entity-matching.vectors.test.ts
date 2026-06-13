/**
 * 共用向量測試（TS 端）。
 *
 * 與 tests/test_entity_matching_vectors.py 讀同一份
 * tests/fixtures/entity_matching_vectors.json。任一端行為漂移即測試紅。
 * 新增案例只改該 JSON，前後端自動同步覆蓋。
 */
import { describe, it, expect } from "vitest";
import { scanEntityMentions } from "@/utils/entity-matching";
// 與 tests/test_entity_matching_vectors.py 讀同一份 JSON（Vite 原生 JSON import，無 node 依賴）
import vectors from "../../../tests/fixtures/entity_matching_vectors.json";

interface VectorCase {
  name: string;
  text: string;
  characters?: Record<string, unknown>;
  clues?: Record<string, unknown>;
  scenes?: Record<string, unknown>;
  expected: { characterNames: string[]; clueNames: string[]; sceneName: string | null };
}

const cases: VectorCase[] = (vectors as { cases: VectorCase[] }).cases;

describe("entity-matching shared vectors", () => {
  for (const c of cases) {
    it(c.name, () => {
      const result = scanEntityMentions(c.text, {
        characters: c.characters ?? {},
        clues: c.clues ?? {},
        scenes: c.scenes ?? {},
      });
      expect([...result.characterNames].sort()).toEqual([...c.expected.characterNames].sort());
      expect([...result.clueNames].sort()).toEqual([...c.expected.clueNames].sort());
      expect(result.sceneName).toBe(c.expected.sceneName);
    });
  }
});
