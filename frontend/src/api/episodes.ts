/**
 * 集數工作流：建立/更新/刪除集、片段、場景、生成劇本/分鏡/影片 等。
 */

import type { EpisodeMeta, EpisodeOverrides, EpisodeScript, ProjectData, Scene } from "@/types";
import { getApi, withScriptFileQuery } from "./_http";
import type { SuccessResponse } from "./types";

type BatchGenerateResponse = {
  enqueued: string[];
  skipped: { id: string; reason: string }[];
};

type SceneBackendPatch = {
  image_backend?: string | null;
  video_backend?: string | null;
};

type SceneBackendResponse = {
  success: boolean;
  scene_id: string;
  image_backend: string | null;
  video_backend: string | null;
};

type SceneCostDiff = {
  current: number;
  next: number;
  delta: number;
  currency: string;
};

type SceneCostEstimateRequest = {
  project_name: string;
  script_file: string;
  scene_id: string;
  image_backend?: string | null;
  video_backend?: string | null;
};

type SceneCostEstimateResponse = {
  scene_id: string;
  duration_seconds: number;
  image: SceneCostDiff;
  video: SceneCostDiff;
};

function buildSceneBackendBody(
  scriptFile: string,
  patch: SceneBackendPatch,
): Record<string, unknown> {
  const body: Record<string, unknown> = { script_file: scriptFile };
  if ("image_backend" in patch) {
    body.set_image = true;
    body.image_backend = patch.image_backend;
  }
  if ("video_backend" in patch) {
    body.set_video = true;
    body.video_backend = patch.video_backend;
  }
  return body;
}

/**
 * 拆段預處理參考來源設定：控制要把哪些 project context 餵給 AI。
 *
 * - `overview` / `style`：boolean 開關。
 * - `characters` / `clues` / `scenes`：
 *   - `null` 表示「全帶」（後端預設行為）。
 *   - `[]` 表示「都不帶」。
 *   - `["A", "B"]` 表示只帶指定名稱。
 */
export type PreprocessRefs = {
  overview: boolean;
  style: boolean;
  characters: string[] | null;
  clues: string[] | null;
  scenes: string[] | null;
};

type RenameResourceResponse = {
  success: boolean;
  old_name: string;
  new_name: string;
  files_moved: number;
  scripts_updated: number;
  versions_updated: number;
};

export const episodesApi = {
  async updateEpisode(
    name: string,
    episode: number,
    updates: { title?: string },
  ): Promise<{ success: boolean }> {
    return getApi().request(
      `/projects/${encodeURIComponent(name)}/episodes/${episode}`,
      {
        method: "PATCH",
        body: JSON.stringify(updates),
      },
    );
  },

  async updateEpisodeOverrides(
    name: string,
    episode: number,
    overrides: EpisodeOverrides,
  ): Promise<{ success: boolean; overrides: EpisodeOverrides }> {
    return getApi().request(
      `/projects/${encodeURIComponent(name)}/episodes/${episode}/overrides`,
      {
        method: "PATCH",
        body: JSON.stringify(overrides),
      },
    );
  },

  async getSourceParagraphs(
    name: string,
    episode: number,
  ): Promise<{ paragraphs: { id: string; content: string }[] }> {
    return getApi().request(
      `/projects/${encodeURIComponent(name)}/episodes/${episode}/source-paragraphs`
    );
  },

  /** 更新某劇集 Step 1 對照表的單一段落（以 segment_id 為錨點精準覆蓋）。 */
  async updateSourceParagraph(
    name: string,
    episode: number,
    segmentId: string,
    content: string,
  ): Promise<{ success: boolean; id: string; content: string }> {
    return getApi().request(
      `/projects/${encodeURIComponent(name)}/episodes/${episode}/source-paragraphs/${encodeURIComponent(segmentId)}`,
      { method: "PUT", body: JSON.stringify({ content }) },
    );
  },

  async createEpisode(
    name: string,
    body: { episode?: number; title?: string } = {},
  ): Promise<{ success: boolean; episode: EpisodeMeta; project: ProjectData }> {
    return getApi().request(`/projects/${encodeURIComponent(name)}/episodes`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  // ==================== 批次生成 ====================

  async batchGenerateStoryboards(
    name: string,
    body: { script_file: string; ids?: string[] | null; force?: boolean },
  ): Promise<BatchGenerateResponse> {
    return getApi().request(
      `/projects/${encodeURIComponent(name)}/generate/storyboards/batch`,
      { method: "POST", body: JSON.stringify(body) },
    );
  },

  async batchGenerateVideos(
    name: string,
    body: { script_file: string; ids?: string[] | null; force?: boolean },
  ): Promise<BatchGenerateResponse> {
    return getApi().request(
      `/projects/${encodeURIComponent(name)}/generate/videos/batch`,
      { method: "POST", body: JSON.stringify(body) },
    );
  },

  async batchGenerateCharacters(
    name: string,
    body: { names?: string[] | null; force?: boolean } = {},
  ): Promise<BatchGenerateResponse> {
    return getApi().request(
      `/projects/${encodeURIComponent(name)}/generate/characters/batch`,
      { method: "POST", body: JSON.stringify(body) },
    );
  },

  async batchGenerateClues(
    name: string,
    body: { names?: string[] | null; force?: boolean } = {},
  ): Promise<BatchGenerateResponse> {
    return getApi().request(
      `/projects/${encodeURIComponent(name)}/generate/clues/batch`,
      { method: "POST", body: JSON.stringify(body) },
    );
  },

  async batchGenerateScenes(
    name: string,
    body: { names?: string[] | null; force?: boolean } = {},
  ): Promise<BatchGenerateResponse> {
    return getApi().request(
      `/projects/${encodeURIComponent(name)}/generate/scenes/batch`,
      { method: "POST", body: JSON.stringify(body) },
    );
  },

  // ==================== 集數工作流 ====================

  async composeEpisode(
    name: string,
    episode: number,
  ): Promise<{ output_path: string; stdout_tail: string; duration_seconds: number }> {
    return getApi().request(
      `/projects/${encodeURIComponent(name)}/episodes/${episode}/compose`,
      { method: "POST", body: JSON.stringify({}) },
    );
  },

  async generateEpisodeScript(
    name: string,
    episode: number,
    model?: string | null,
    instruction?: string | null,
  ): Promise<{ script_file: string; segments_count: number }> {
    const body: Record<string, unknown> = { model: model || null };
    const trimmed = (instruction || "").trim();
    if (trimmed) body.instruction = trimmed;
    return getApi().request(
      `/projects/${encodeURIComponent(name)}/episodes/${episode}/script`,
      { method: "POST", body: JSON.stringify(body) },
    );
  },

  async preprocessEpisode(
    name: string,
    episode: number,
    source?: string,
    refs?: PreprocessRefs,
    numSegments?: number,
    model?: string | null,
    instruction?: string,
  ): Promise<{ step1_path: string; content_mode: string }> {
    const body: Record<string, unknown> = { source };
    if (refs !== undefined) body.refs = refs;
    if (numSegments !== undefined) body.num_segments = numSegments;
    if (model) body.model = model;
    if (instruction) body.instruction = instruction;
    return getApi().request(
      `/projects/${encodeURIComponent(name)}/episodes/${episode}/preprocess`,
      { method: "POST", body: JSON.stringify(body) },
    );
  },

  async addEpisodeSegment(
    name: string,
    episode: number,
  ): Promise<{ segment: unknown; segments_count: number }> {
    return getApi().request(
      `/projects/${encodeURIComponent(name)}/episodes/${episode}/segments`,
      { method: "POST", body: JSON.stringify({}) },
    );
  },

  async addEpisodeScene(
    name: string,
    episode: number,
  ): Promise<{ scene: unknown; scenes_count: number }> {
    return getApi().request(
      `/projects/${encodeURIComponent(name)}/episodes/${episode}/scenes`,
      { method: "POST", body: JSON.stringify({}) },
    );
  },

  /** 依傳入的集數順序重設顯示順序（後端寫到每個 episode 的 ``order`` 欄位）。 */
  async reorderEpisodes(
    name: string,
    episodeNumbers: number[],
  ): Promise<{ success: boolean; project: ProjectData }> {
    return getApi().request(
      `/projects/${encodeURIComponent(name)}/episodes/order`,
      { method: "PATCH", body: JSON.stringify({ episodes: episodeNumbers }) },
    );
  },

  /** 刪除一整集（劇本檔、預處理草稿、分鏡/影片/縮圖、版本檔、合成輸出），並從 project.json 移除。 */
  async deleteEpisode(
    name: string,
    episode: number,
  ): Promise<{
    success: boolean;
    episode: number;
    removed: string[];
    project: ProjectData;
  }> {
    return getApi().request(
      `/projects/${encodeURIComponent(name)}/episodes/${episode}`,
      { method: "DELETE" },
    );
  },

  /** 清空指定劇集的劇本內容（重置為空骨架），保留劇集條目與預處理草稿。 */
  async resetEpisodeScript(
    name: string,
    episode: number,
  ): Promise<{ success: boolean; episode: number; content_mode: string }> {
    return getApi().request(
      `/projects/${encodeURIComponent(name)}/episodes/${episode}/script`,
      { method: "DELETE" },
    );
  },

  /** 刪除說書模式劇本中的一個片段。 */
  async deleteSegment(
    name: string,
    segmentId: string,
    scriptFile: string,
  ): Promise<{ success: boolean; segments_count: number }> {
    const path = `/projects/${encodeURIComponent(name)}/segments/${encodeURIComponent(segmentId)}`;
    return getApi().request(
      withScriptFileQuery(path, scriptFile),
      { method: "DELETE" },
    );
  },

  /** 刪除劇集動畫模式劇本中的一個場景。 */
  async deleteScene(
    name: string,
    sceneId: string,
    scriptFile: string,
  ): Promise<{ success: boolean; scenes_count: number }> {
    const path = `/projects/${encodeURIComponent(name)}/scenes/${encodeURIComponent(sceneId)}`;
    return getApi().request(
      withScriptFileQuery(path, scriptFile),
      { method: "DELETE" },
    );
  },

  // ==================== 角色管理 ====================

  async addCharacter(
    projectName: string,
    name: string,
    description: string,
    voiceStyle: string = "",
  ): Promise<SuccessResponse> {
    return getApi().request(
      `/projects/${encodeURIComponent(projectName)}/characters`,
      {
        method: "POST",
        body: JSON.stringify({
          name,
          description,
          voice_style: voiceStyle,
        }),
      },
    );
  },

  async updateCharacter(
    projectName: string,
    charName: string,
    updates: Record<string, unknown>,
  ): Promise<SuccessResponse> {
    return getApi().request(
      `/projects/${encodeURIComponent(projectName)}/characters/${encodeURIComponent(charName)}`,
      {
        method: "PATCH",
        body: JSON.stringify(updates),
      },
    );
  },

  async deleteCharacter(
    projectName: string,
    charName: string,
  ): Promise<SuccessResponse> {
    return getApi().request(
      `/projects/${encodeURIComponent(projectName)}/characters/${encodeURIComponent(charName)}`,
      { method: "DELETE" },
    );
  },

  async renameCharacter(
    projectName: string,
    oldName: string,
    newName: string,
  ): Promise<RenameResourceResponse> {
    return getApi().request(
      `/projects/${encodeURIComponent(projectName)}/characters/${encodeURIComponent(oldName)}/rename`,
      { method: "POST", body: JSON.stringify({ new_name: newName }) },
    );
  },

  // ==================== 線索管理 ====================

  async addClue(
    projectName: string,
    name: string,
    description: string,
    importance: string = "major",
  ): Promise<SuccessResponse> {
    return getApi().request(
      `/projects/${encodeURIComponent(projectName)}/clues`,
      {
        method: "POST",
        body: JSON.stringify({
          name,
          description,
          importance,
        }),
      },
    );
  },

  async updateClue(
    projectName: string,
    clueName: string,
    updates: Record<string, unknown>,
  ): Promise<SuccessResponse> {
    return getApi().request(
      `/projects/${encodeURIComponent(projectName)}/clues/${encodeURIComponent(clueName)}`,
      {
        method: "PATCH",
        body: JSON.stringify(updates),
      },
    );
  },

  async deleteClue(
    projectName: string,
    clueName: string,
  ): Promise<SuccessResponse> {
    return getApi().request(
      `/projects/${encodeURIComponent(projectName)}/clues/${encodeURIComponent(clueName)}`,
      { method: "DELETE" },
    );
  },

  async renameClue(
    projectName: string,
    oldName: string,
    newName: string,
  ): Promise<RenameResourceResponse> {
    return getApi().request(
      `/projects/${encodeURIComponent(projectName)}/clues/${encodeURIComponent(oldName)}/rename`,
      { method: "POST", body: JSON.stringify({ new_name: newName }) },
    );
  },

  // ==================== 專案場景管理（project.json scenes） ====================
  //
  // 注意：本檔已有 `deleteScene`（L~180）負責刪除「劇集動畫模式劇本」中
  // 的單一分鏡 scene（scene_id），語意完全不同。為避免覆蓋既有 export，
  // 專案層級場景實體 CRUD 一律使用 `*ProjectScene` 命名，API path
  // 也使用 `/project-scenes` 避免撞到劇本內分鏡 `/scenes/{scene_id}`。

  async addProjectScene(
    projectName: string,
    name: string,
    description: string,
  ): Promise<{ success: boolean; scene: Scene }> {
    return getApi().request(
      `/projects/${encodeURIComponent(projectName)}/project-scenes`,
      {
        method: "POST",
        body: JSON.stringify({ name, description }),
      },
    );
  },

  async updateProjectScene(
    projectName: string,
    sceneName: string,
    updates: Partial<Scene>,
  ): Promise<{ success: boolean; scene: Scene }> {
    return getApi().request(
      `/projects/${encodeURIComponent(projectName)}/project-scenes/${encodeURIComponent(sceneName)}`,
      {
        method: "PATCH",
        body: JSON.stringify(updates),
      },
    );
  },

  async deleteProjectScene(
    projectName: string,
    sceneName: string,
  ): Promise<{ success: boolean; message: string }> {
    return getApi().request(
      `/projects/${encodeURIComponent(projectName)}/project-scenes/${encodeURIComponent(sceneName)}`,
      { method: "DELETE" },
    );
  },

  async renameProjectScene(
    projectName: string,
    oldName: string,
    newName: string,
  ): Promise<RenameResourceResponse> {
    return getApi().request(
      `/projects/${encodeURIComponent(projectName)}/project-scenes/${encodeURIComponent(oldName)}/rename`,
      { method: "POST", body: JSON.stringify({ new_name: newName }) },
    );
  },

  // ==================== 場景管理 ====================

  async getScript(
    projectName: string,
    scriptFile: string,
  ): Promise<EpisodeScript> {
    return getApi().request(
      `/projects/${encodeURIComponent(projectName)}/scripts/${encodeURIComponent(scriptFile)}`,
    );
  },

  async updateScene(
    projectName: string,
    sceneId: string,
    scriptFile: string,
    updates: Record<string, unknown>,
  ): Promise<SuccessResponse> {
    return getApi().request(
      `/projects/${encodeURIComponent(projectName)}/scenes/${encodeURIComponent(sceneId)}`,
      {
        method: "PATCH",
        body: JSON.stringify({ script_file: scriptFile, updates }),
      },
    );
  },

  // ==================== 片段管理（說書模式） ====================

  async updateSegment(
    projectName: string,
    segmentId: string,
    updates: Record<string, unknown>,
  ): Promise<SuccessResponse> {
    return getApi().request(
      `/projects/${encodeURIComponent(projectName)}/segments/${encodeURIComponent(segmentId)}`,
      {
        method: "PATCH",
        body: JSON.stringify(updates),
      },
    );
  },

  // ==================== Scene-level Backend 覆蓋 ====================

  /**
   * 設定 scene 的 image_backend / video_backend 覆蓋。
   * 傳入 undefined 表示不動該欄位；傳入 null 表示清除覆蓋（沿用上層）。
   */
  async updateSceneBackend(
    projectName: string,
    episode: number,
    sceneId: string,
    scriptFile: string,
    patch: SceneBackendPatch,
  ): Promise<SceneBackendResponse> {
    return getApi().request(
      `/projects/${encodeURIComponent(projectName)}/episodes/${episode}/scenes/${encodeURIComponent(sceneId)}/backend`,
      { method: "PATCH", body: JSON.stringify(buildSceneBackendBody(scriptFile, patch)) },
    );
  },

  /** 計算 scene 套用候選 backend 後的費用差異。 */
  async estimateSceneCost(payload: SceneCostEstimateRequest): Promise<SceneCostEstimateResponse> {
    return getApi().request(`/cost-estimation/scene`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  // ==================== 生成 API ====================

  /** 生成分鏡圖 */
  async generateStoryboard(
    projectName: string,
    segmentId: string,
    prompt: string | Record<string, unknown>,
    scriptFile: string,
  ): Promise<{ success: boolean; task_id: string; message: string }> {
    return getApi().request(
      `/projects/${encodeURIComponent(projectName)}/generate/storyboard/${encodeURIComponent(segmentId)}`,
      {
        method: "POST",
        body: JSON.stringify({ prompt, script_file: scriptFile }),
      },
    );
  },

  /** 生成影片 */
  async generateVideo(
    projectName: string,
    segmentId: string,
    prompt: string | Record<string, unknown>,
    scriptFile: string,
    durationSeconds: number = 4,
  ): Promise<{ success: boolean; task_id: string; message: string }> {
    return getApi().request(
      `/projects/${encodeURIComponent(projectName)}/generate/video/${encodeURIComponent(segmentId)}`,
      {
        method: "POST",
        body: JSON.stringify({
          prompt,
          script_file: scriptFile,
          duration_seconds: durationSeconds,
        }),
      },
    );
  },

  /** 生成角色設計圖 */
  async generateCharacter(
    projectName: string,
    charName: string,
    prompt: string,
  ): Promise<{ success: boolean; task_id: string; message: string }> {
    return getApi().request(
      `/projects/${encodeURIComponent(projectName)}/generate/character/${encodeURIComponent(charName)}`,
      {
        method: "POST",
        body: JSON.stringify({ prompt }),
      },
    );
  },

  /** 生成線索設計圖 */
  async generateClue(
    projectName: string,
    clueName: string,
    prompt: string,
  ): Promise<{ success: boolean; task_id: string; message: string }> {
    return getApi().request(
      `/projects/${encodeURIComponent(projectName)}/generate/clue/${encodeURIComponent(clueName)}`,
      {
        method: "POST",
        body: JSON.stringify({ prompt }),
      },
    );
  },

  /** 生成場景設計圖 */
  async generateScene(
    projectName: string,
    sceneName: string,
    prompt: string,
  ): Promise<{ success: boolean; task_id: string; message: string }> {
    return getApi().request(
      `/projects/${encodeURIComponent(projectName)}/generate/scene/${encodeURIComponent(sceneName)}`,
      {
        method: "POST",
        body: JSON.stringify({ prompt }),
      },
    );
  },

  /** AI 輔助生成/最佳化角色、道具、場景繪圖提示詞 */
  async generateAIDescription(
    projectName: string,
    payload: {
      type: "character" | "clue" | "scene" | "image_prompt" | "video_prompt";
      name?: string;
      description: string;
      instruction?: string;
      model?: string;
    },
  ): Promise<{ success: boolean; prompt: string }> {
    return getApi().request(
      `/projects/${encodeURIComponent(projectName)}/helper/generate-prompt`,
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
    );
  },
};
