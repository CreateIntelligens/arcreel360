import { describe, it, expect } from "vitest";

import { sortEpisodesForDisplay } from "./episodes";

const make = (episode: number, order?: number) => ({
  episode,
  title: `E${episode}`,
  script_file: `scripts/episode_${episode}.json`,
  ...(order !== undefined ? { order } : {}),
});

describe("sortEpisodesForDisplay", () => {
  it("uses `order` when present", () => {
    const result = sortEpisodesForDisplay([
      make(3, 2),
      make(1, 0),
      make(2, 1),
    ]);
    expect(result.map((e) => e.episode)).toEqual([1, 2, 3]);
  });

  it("falls back to `episode` when no order is set", () => {
    const result = sortEpisodesForDisplay([make(3), make(1), make(2)]);
    expect(result.map((e) => e.episode)).toEqual([1, 2, 3]);
  });

  it("mixes ordered and unordered entries using order || episode as key", () => {
    // ep=5 no order → key 5; ep=2 order=0 → key 0; ep=10 order=3 → key 3
    const result = sortEpisodesForDisplay([
      make(5),
      make(2, 0),
      make(10, 3),
    ]);
    expect(result.map((e) => e.episode)).toEqual([2, 10, 5]);
  });

  it("is stable when sort keys tie", () => {
    // Two entries both fall back to key 1 — preserve input order.
    const result = sortEpisodesForDisplay([
      { episode: 1, title: "a", script_file: "" },
      { episode: 1, title: "b", script_file: "" },
    ]);
    expect(result.map((e) => e.title)).toEqual(["a", "b"]);
  });
});
