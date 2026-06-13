import type { ProjectChange } from "@/types";

const GROUP_NAME_LIMIT = 5;

const ENTITY_LABELS: Record<ProjectChange["entity_type"], string> = {
  project: "專案",
  character: "角色",
  clue: "道具",
  segment: "分鏡",
  episode: "劇本",
  overview: "專案總覽",
  draft: "預處理",
};

export interface GroupedProjectChange {
  key: string;
  entityType: ProjectChange["entity_type"];
  action: ProjectChange["action"];
  changes: ProjectChange[];
}

export function buildEntityRevisionKey(
  entityType: ProjectChange["entity_type"],
  entityId: string,
): string {
  return `${entityType}:${entityId}`;
}

export function buildStep1DraftRevisionKey(episode: number): string {
  return buildEntityRevisionKey("draft", `episode_${episode}_step1`);
}

export function buildVersionResourceRevisionKey(
  resourceType: "storyboards" | "videos" | "characters" | "clues" | "scenes",
  resourceId: string,
): string {
  if (resourceType === "storyboards" || resourceType === "videos") {
    return buildEntityRevisionKey("segment", resourceId);
  }
  if (resourceType === "characters") {
    return buildEntityRevisionKey("character", resourceId);
  }
  if (resourceType === "scenes") {
    // ProjectChange.entity_type 尚無 "scene"，無法走 entity revision
    // 失效路徑（同 StudioCanvasRouter.handleSaveScene 的處理）。這裡仍
    // 回傳穩定的 scene 專屬 key，呼叫端用 refreshProject() 重抓快取。
    return `scene:${resourceId}`;
  }
  return buildEntityRevisionKey("clue", resourceId);
}

export function groupChangesByType(
  changes: ProjectChange[],
): GroupedProjectChange[] {
  const groups = new Map<string, GroupedProjectChange>();

  for (const change of changes) {
    const key = `${change.entity_type}:${change.action}`;
    const existing = groups.get(key);
    if (existing) {
      existing.changes.push(change);
      continue;
    }
    groups.set(key, {
      key,
      entityType: change.entity_type,
      action: change.action,
      changes: [change],
    });
  }

  return [...groups.values()];
}

function getEntityLabel(group: GroupedProjectChange): string {
  if (group.action === "storyboard_ready") {
    return "分鏡圖";
  }
  if (group.action === "video_ready") {
    return "影片";
  }
  return ENTITY_LABELS[group.entityType] ?? "內容";
}

function getChangeListLabel(change: ProjectChange): string {
  if (
    change.entity_type === "character" ||
    change.entity_type === "clue" ||
    change.entity_type === "segment"
  ) {
    return change.entity_id;
  }
  return change.label;
}

function summarizeGroupNames(group: GroupedProjectChange): string {
  const names = group.changes.slice(0, GROUP_NAME_LIMIT).map(getChangeListLabel);
  const suffix = group.changes.length > GROUP_NAME_LIMIT ? "…等" : "";
  return `${names.join("、")}${suffix}`;
}

function formatSingleNotificationText(change: ProjectChange): string {
  if (change.action === "storyboard_ready") {
    return `${change.label}的分鏡圖已生成`;
  }
  if (change.action === "video_ready") {
    return `${change.label}的影片已生成`;
  }
  if (change.action === "created") {
    return `${change.label}已建立`;
  }
  if (change.action === "deleted") {
    return `${change.label}已刪除`;
  }
  return `${change.label}已更新`;
}

function formatSingleDeferredText(change: ProjectChange): string {
  if (change.action === "storyboard_ready") {
    return `AI 剛生成了 ${change.label} 的分鏡圖，點選檢視`;
  }
  if (change.action === "video_ready") {
    return `AI 剛生成了 ${change.label} 的影片，點選檢視`;
  }
  if (change.action === "created") {
    return `AI 剛新增了 ${change.label}，點選檢視`;
  }
  if (change.action === "deleted") {
    return `AI 剛刪除了 ${change.label}，點選檢視`;
  }
  return `AI 剛更新了 ${change.label}，點選檢視`;
}

export function formatGroupedNotificationText(
  group: GroupedProjectChange,
): string {
  if (group.changes.length === 1) {
    return formatSingleNotificationText(group.changes[0]);
  }

  const count = group.changes.length;
  const entityLabel = getEntityLabel(group);
  const summary = summarizeGroupNames(group);

  if (group.action === "storyboard_ready" || group.action === "video_ready") {
    return `已生成 ${count} 個${entityLabel}：${summary}`;
  }
  if (group.action === "created") {
    return `新增了 ${count} 個${entityLabel}：${summary}`;
  }
  if (group.action === "deleted") {
    return `刪除了 ${count} 個${entityLabel}：${summary}`;
  }
  return `更新了 ${count} 個${entityLabel}：${summary}`;
}

export function formatGroupedDeferredText(
  group: GroupedProjectChange,
): string {
  if (group.changes.length === 1) {
    return formatSingleDeferredText(group.changes[0]);
  }

  const count = group.changes.length;
  const entityLabel = getEntityLabel(group);
  const summary = summarizeGroupNames(group);

  if (group.action === "storyboard_ready" || group.action === "video_ready") {
    return `AI 剛生成了 ${count} 個${entityLabel}：${summary}，點選檢視`;
  }
  if (group.action === "created") {
    return `AI 剛新增了 ${count} 個${entityLabel}：${summary}，點選檢視`;
  }
  if (group.action === "deleted") {
    return `AI 剛刪除了 ${count} 個${entityLabel}：${summary}，點選檢視`;
  }
  return `AI 剛更新了 ${count} 個${entityLabel}：${summary}，點選檢視`;
}
