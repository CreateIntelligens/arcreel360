import { describe, expect, it } from "vitest";
import type { ProjectChange } from "@/types";
import {
  formatGroupedDeferredText,
  formatGroupedNotificationText,
  groupChangesByType,
} from "./project-changes";

function makeChange(overrides: Partial<ProjectChange> = {}): ProjectChange {
  return {
    entity_type: "character",
    action: "created",
    entity_id: "張三",
    label: "角色「張三」",
    important: true,
    focus: null,
    ...overrides,
  };
}

describe("project-changes utils", () => {
  it("groups changes by entity_type and action", () => {
    const groups = groupChangesByType([
      makeChange({ entity_id: "張三", label: "角色「張三」" }),
      makeChange({ entity_id: "李四", label: "角色「李四」" }),
      makeChange({
        entity_type: "clue",
        entity_id: "玉佩",
        label: "道具「玉佩」",
      }),
      makeChange({
        entity_type: "character",
        action: "updated",
        entity_id: "王五",
        label: "角色「王五」",
      }),
    ]);

    expect(groups).toHaveLength(3);
    expect(groups[0]).toMatchObject({
      key: "character:created",
      changes: [expect.objectContaining({ entity_id: "張三" }), expect.objectContaining({ entity_id: "李四" })],
    });
    expect(groups[1].key).toBe("clue:created");
    expect(groups[2].key).toBe("character:updated");
  });

  it("formats grouped notification text and truncates long lists", () => {
    const [singleGroup] = groupChangesByType([
      makeChange({ entity_id: "張三", label: "角色「張三」" }),
    ]);
    expect(formatGroupedNotificationText(singleGroup)).toBe("角色「張三」已建立");

    const [grouped] = groupChangesByType([
      makeChange({ entity_id: "張三", label: "角色「張三」" }),
      makeChange({ entity_id: "李四", label: "角色「李四」" }),
      makeChange({ entity_id: "王五", label: "角色「王五」" }),
      makeChange({ entity_id: "趙六", label: "角色「趙六」" }),
      makeChange({ entity_id: "錢七", label: "角色「錢七」" }),
      makeChange({ entity_id: "孫八", label: "角色「孫八」" }),
    ]);

    expect(formatGroupedNotificationText(grouped)).toBe(
      "新增了 6 個角色：張三、李四、王五、趙六、錢七…等",
    );
    expect(formatGroupedDeferredText(grouped)).toBe(
      "AI 剛新增了 6 個角色：張三、李四、王五、趙六、錢七…等，點選檢視",
    );
  });
});
