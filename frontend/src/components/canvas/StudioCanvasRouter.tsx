import { useState, useCallback, useMemo, useEffect } from "react";
import { Route, Switch, Redirect, useLocation } from "wouter";
import { useProjectsStore } from "@/stores/projects-store";
import { useAppStore } from "@/stores/app-store";
import { useTasksStore } from "@/stores/tasks-store";
import { LorebookGallery } from "./lorebook/LorebookGallery";
import { TimelineCanvas } from "./timeline/TimelineCanvas";
import { OverviewCanvas } from "./OverviewCanvas";
import { SourceFileViewer } from "./SourceFileViewer";
import { API } from "@/api";
import { lookupDefaultResolution } from "@/utils/provider-models";
import { resolveEpisodeContentMode } from "@/utils/content-mode";
import { buildEntityRevisionKey, buildStep1DraftRevisionKey } from "@/utils/project-changes";
import type { Clue, EpisodeScript, TaskItem } from "@/types";

// ---------------------------------------------------------------------------
// StudioCanvasRouter — reads Zustand store data and renders the correct
// canvas view based on the nested route within /app/projects/:projectName.
// ---------------------------------------------------------------------------

const ACTIVE_TASK_STATUSES = new Set<TaskItem["status"]>(["queued", "running"]);
type LorebookMode = "characters" | "clues" | "scenes";
type ReferenceResourceType = "characters" | "clues" | "scenes";

const LOREBOOK_MODE_BY_ROUTE: Record<string, LorebookMode> = {
  "/characters": "characters",
  "/clues": "clues",
  "/scenes": "scenes",
};

interface GeneratingResources {
  characterNames: Set<string>;
  clueNames: Set<string>;
  sceneNames: Set<string>;
  storyboardIds: Set<string>;
  videoIds: Set<string>;
}

type SegmentUpdateExtras = Record<string, unknown>;
const PREPROCESSING_SOURCE_FIELDS = new Set(["novel_text", "scene_description"]);

function getEpisodeFromScriptFile(scriptFile: string | undefined): number | null {
  const match = scriptFile?.match(/episode_(\d+)/i);
  if (!match) return null;
  const episode = Number.parseInt(match[1], 10);
  return Number.isFinite(episode) ? episode : null;
}

function getPreprocessingDraftInvalidationKey(
  field: string,
  activeScript: EpisodeScript | undefined,
  scriptFile: string | undefined,
): string | null {
  if (!PREPROCESSING_SOURCE_FIELDS.has(field)) {
    return null;
  }

  const episode = typeof activeScript?.episode === "number"
    ? activeScript.episode
    : getEpisodeFromScriptFile(scriptFile);

  return episode != null ? buildStep1DraftRevisionKey(episode) : null;
}

function collectGeneratingResources(
  tasks: TaskItem[],
  projectName: string | null | undefined,
): GeneratingResources {
  const resources: GeneratingResources = {
    characterNames: new Set<string>(),
    clueNames: new Set<string>(),
    sceneNames: new Set<string>(),
    storyboardIds: new Set<string>(),
    videoIds: new Set<string>(),
  };

  for (const task of tasks) {
    if (
      task.project_name !== projectName ||
      !ACTIVE_TASK_STATUSES.has(task.status)
    ) {
      continue;
    }

    switch (task.task_type) {
      case "character":
        resources.characterNames.add(task.resource_id);
        break;
      case "clue":
        resources.clueNames.add(task.resource_id);
        break;
      case "scene":
        resources.sceneNames.add(task.resource_id);
        break;
      case "storyboard":
        resources.storyboardIds.add(task.resource_id);
        break;
      case "video":
        resources.videoIds.add(task.resource_id);
        break;
    }
  }

  return resources;
}

export function StudioCanvasRouter() {
  const { currentProjectData, currentProjectName, currentScripts } =
    useProjectsStore();

  const currentVideoResolution = useMemo(() => {
    const backend = currentProjectData?.video_backend;
    if (!backend || !backend.includes("/")) return null;
    const modelId = backend.split("/")[1];
    return currentProjectData?.video_model_settings?.[modelId]?.resolution ??
      lookupDefaultResolution(backend) ??
      null;
  }, [currentProjectData?.video_backend, currentProjectData?.video_model_settings]);

  // 從任務佇列派生 loading 狀態（替代本地 state）
  const tasks = useTasksStore((s) => s.tasks);
  const generatingResources = useMemo(
    () => collectGeneratingResources(tasks, currentProjectName),
    [tasks, currentProjectName],
  );

  // 重新整理專案資料
  const refreshProject = useCallback(async (invalidateKeys: string[] = []) => {
    if (!currentProjectName) return;
    try {
      const res = await API.getProject(currentProjectName);
      useProjectsStore.getState().setCurrentProject(
        currentProjectName,
        res.project,
        res.scripts ?? {},
        res.asset_fingerprints,
      );
      if (invalidateKeys.length > 0) {
        useAppStore.getState().invalidateEntities(invalidateKeys);
      }
    } catch {
      // 靜默失敗
    }
  }, [currentProjectName]);

  // ---- Timeline action callbacks ----
  // These receive scriptFile from TimelineCanvas so they always use the active episode's script.
  const handleUpdatePrompt = useCallback(async (
    segmentId: string,
    field: string,
    value: unknown,
    scriptFile?: string,
    extraUpdates?: SegmentUpdateExtras,
  ) => {
    if (!currentProjectName) return;

    // 檢查更新的值是否為空 (不能留空儲存)
    const isValueEmpty = (val: unknown, fieldName: string): boolean => {
      if (fieldName === "image_prompt") {
        if (!val) return true;
        if (typeof val === "string") return !val.trim();
        if (typeof val === "object") {
          const p = val as { scene?: string };
          return !p.scene || !p.scene.trim();
        }
      }
      if (fieldName === "video_prompt") {
        if (!val) return true;
        if (typeof val === "string") return !val.trim();
        if (typeof val === "object") {
          const p = val as { action?: string };
          return !p.action || !p.action.trim();
        }
      }
      return false;
    };

    if (field === "image_prompt" && isValueEmpty(value, "image_prompt")) {
      useAppStore.getState().pushToast("分鏡圖描述（Image Prompt）不能為空！儲存失敗。", "warning");
      return;
    }
    if (field === "video_prompt" && isValueEmpty(value, "video_prompt")) {
      useAppStore.getState().pushToast("影片描述（Video Prompt）不能為空！儲存失敗。", "warning");
      return;
    }

    const activeScript = scriptFile ? currentScripts?.[scriptFile] : undefined;
    const mode = resolveEpisodeContentMode(activeScript, currentProjectData?.content_mode);
    const updates = { [field]: value, ...(extraUpdates ?? {}) };
    const draftInvalidationKey = getPreprocessingDraftInvalidationKey(field, activeScript, scriptFile);
    try {
      if (mode === "drama") {
        await API.updateScene(currentProjectName, segmentId, scriptFile ?? "", updates);
      } else {
        await API.updateSegment(currentProjectName, segmentId, {
          script_file: scriptFile,
          ...updates,
        });
      }
      await refreshProject(draftInvalidationKey ? [draftInvalidationKey] : []);
    } catch (err) {
      useAppStore.getState().pushToast(`更新 Prompt 失敗: ${(err as Error).message}`, "error");
    }
  }, [currentProjectName, currentProjectData, currentScripts, refreshProject]);

  const handleGenerateStoryboard = useCallback(async (segmentId: string, scriptFile?: string) => {
    if (!currentProjectName || !currentScripts) return;
    const resolvedFile = scriptFile ?? Object.keys(currentScripts)[0];
    if (!resolvedFile) return;
    const script = currentScripts[resolvedFile];
    if (!script) return;
    const segments = ("segments" in script ? script.segments : undefined) ??
      ("scenes" in script ? script.scenes : undefined) ?? [];
    const seg = segments.find((s) => {
      const id = "segment_id" in s ? s.segment_id : (s as { scene_id?: string }).scene_id ?? "";
      return id === segmentId;
    });
    const prompt = seg?.image_prompt ?? "";

    // 檢查 Prompt 是否為空
    const isPromptEmpty = (p: unknown): boolean => {
      if (!p) return true;
      if (typeof p === "string") return !p.trim();
      if (typeof p === "object") {
        const o = p as { scene?: string };
        return !o.scene || !o.scene.trim();
      }
      return true;
    };

    if (isPromptEmpty(prompt)) {
      useAppStore.getState().pushToast("無法提交：分鏡圖描述為空，請先填寫描述！", "error");
      return;
    }

    try {
      await API.generateStoryboard(currentProjectName, segmentId, prompt as string | Record<string, unknown>, resolvedFile);
      useAppStore.getState().pushToast(`已提交分鏡「${segmentId}」生成任務`, "success");
    } catch (err) {
      useAppStore.getState().pushToast(`生圖失敗: ${(err as Error).message}`, "error");
    }
  }, [currentProjectName, currentScripts]);

  const handleGenerateVideo = useCallback(async (segmentId: string, scriptFile?: string) => {
    if (!currentProjectName || !currentScripts) return;
    const resolvedFile = scriptFile ?? Object.keys(currentScripts)[0];
    if (!resolvedFile) return;
    const script = currentScripts[resolvedFile];
    if (!script) return;
    const segments = ("segments" in script ? script.segments : undefined) ??
      ("scenes" in script ? script.scenes : undefined) ?? [];
    const seg = segments.find((s) => {
      const id = "segment_id" in s ? s.segment_id : (s as { scene_id?: string }).scene_id ?? "";
      return id === segmentId;
    });
    const prompt = seg?.video_prompt ?? "";
    const duration = seg?.duration_seconds ?? 4;

    // 檢查 Prompt 是否為空
    const isPromptEmpty = (p: unknown): boolean => {
      if (!p) return true;
      if (typeof p === "string") return !p.trim();
      if (typeof p === "object") {
        const o = p as { action?: string };
        return !o.action || !o.action.trim();
      }
      return true;
    };

    if (isPromptEmpty(prompt)) {
      useAppStore.getState().pushToast("無法提交：影片描述為空，請先填寫描述！", "error");
      return;
    }

    try {
      await API.generateVideo(currentProjectName, segmentId, prompt as string | Record<string, unknown>, resolvedFile, duration);
      useAppStore.getState().pushToast(`已提交影片「${segmentId}」生成任務`, "success");
    } catch (err) {
      useAppStore.getState().pushToast(`生成影片失敗: ${(err as Error).message}`, "error");
    }
  }, [currentProjectName, currentScripts]);

  // ---- Character CRUD callbacks ----
  const handleSaveCharacter = useCallback(async (
    name: string,
    payload: {
      description: string;
      voiceStyle: string;
      imageBackend?: string | null;
    },
  ) => {
    if (!currentProjectName) return;
    try {
      await API.updateCharacter(currentProjectName, name, {
        description: payload.description,
        voice_style: payload.voiceStyle,
        image_backend: payload.imageBackend,
      });

      await refreshProject();
      useAppStore.getState().pushToast(`角色「${name}」已更新`, "success");
    } catch (err) {
      useAppStore.getState().pushToast(`更新角色失敗: ${(err as Error).message}`, "error");
    }
  }, [currentProjectName, refreshProject]);

  const handleUploadCharacterReference = useCallback(
    async (name: string, file: File) => {
      if (!currentProjectName) return;
      try {
        await API.uploadFile(currentProjectName, "character_ref", file, name);
        await refreshProject([buildEntityRevisionKey("character", name)]);
        useAppStore.getState().pushToast(`角色「${name}」參考圖已上傳`, "success");
      } catch (err) {
        useAppStore
          .getState()
          .pushToast(`上傳參考圖失敗: ${(err as Error).message}`, "error");
      }
    },
    [currentProjectName, refreshProject],
  );

  const removeReferenceImage = useCallback(
    async (
      resourceType: ReferenceResourceType,
      name: string,
      successMessage: string,
      invalidateKeys: string[] = [],
    ) => {
      if (!currentProjectName) return;
      try {
        await API.deleteReferenceImage(currentProjectName, resourceType, name);
        await refreshProject(invalidateKeys);
        useAppStore.getState().pushToast(successMessage, "success");
      } catch (err) {
        useAppStore
          .getState()
          .pushToast(`移除參考圖失敗: ${(err as Error).message}`, "error");
      }
    },
    [currentProjectName, refreshProject],
  );

  const handleRemoveCharacterReference = useCallback(
    async (name: string) => {
      await removeReferenceImage(
        "characters",
        name,
        `角色「${name}」參考圖已移除`,
        [buildEntityRevisionKey("character", name)],
      );
    },
    [removeReferenceImage],
  );

  const handleGenerateCharacter = useCallback(async (name: string) => {
    if (!currentProjectName) return;
    try {
      await API.generateCharacter(
        currentProjectName,
        name,
        currentProjectData?.characters?.[name]?.description || name,
      );
      useAppStore
        .getState()
        .pushToast(`角色「${name}」生成任務已提交`, "success");
    } catch (err) {
      useAppStore.getState().pushToast(`提交失敗: ${(err as Error).message}`, "error");
    }
  }, [currentProjectName, currentProjectData]);

  const handleAddCharacterSubmit = useCallback(async (
    name: string,
    description: string,
    voiceStyle: string,
    referenceFile?: File | null,
  ) => {
    if (!currentProjectName) return;
    try {
      await API.addCharacter(currentProjectName, name, description, voiceStyle);

      if (referenceFile) {
        await API.uploadFile(currentProjectName, "character_ref", referenceFile, name);
      }

      await refreshProject(
        referenceFile
          ? [buildEntityRevisionKey("character", name)]
          : [],
      );
      useAppStore.getState().pushToast(`角色「${name}」已新增`, "success");
    } catch (err) {
      useAppStore.getState().pushToast(`新增失敗: ${(err as Error).message}`, "error");
    }
  }, [currentProjectName, refreshProject]);

  // ---- Clue CRUD callbacks ----
  const handleUpdateClue = useCallback(async (name: string, updates: Partial<Clue>) => {
    if (!currentProjectName) return;
    try {
      await API.updateClue(currentProjectName, name, updates);
      await refreshProject();
      useAppStore.getState().pushToast(`道具「${name}」已更新`, "success");
    } catch (err) {
      useAppStore.getState().pushToast(`更新道具失敗: ${(err as Error).message}`, "error");
    }
  }, [currentProjectName, refreshProject]);

  const handleGenerateClue = useCallback(async (name: string) => {
    if (!currentProjectName) return;
    try {
      await API.generateClue(
        currentProjectName,
        name,
        currentProjectData?.clues?.[name]?.description || name,
      );
      useAppStore
        .getState()
        .pushToast(`道具「${name}」生成任務已提交`, "success");
    } catch (err) {
      useAppStore.getState().pushToast(`提交失敗: ${(err as Error).message}`, "error");
    }
  }, [currentProjectName, currentProjectData]);

  const handleDeleteCharacter = useCallback(async (name: string) => {
    if (!currentProjectName) return;
    try {
      await API.deleteCharacter(currentProjectName, name);
      await refreshProject();
      useAppStore.getState().pushToast(`角色「${name}」已刪除`, "success");
    } catch (err) {
      useAppStore.getState().pushToast(`刪除角色失敗: ${(err as Error).message}`, "error");
    }
  }, [currentProjectName, refreshProject]);

  const handleDeleteClue = useCallback(async (name: string) => {
    if (!currentProjectName) return;
    try {
      await API.deleteClue(currentProjectName, name);
      await refreshProject();
      useAppStore.getState().pushToast(`道具「${name}」已刪除`, "success");
    } catch (err) {
      useAppStore.getState().pushToast(`刪除失敗: ${(err as Error).message}`, "error");
    }
  }, [currentProjectName, refreshProject]);

  const handleRenameCharacter = useCallback(async (oldName: string, newName: string) => {
    if (!currentProjectName) return;
    try {
      const res = await API.renameCharacter(currentProjectName, oldName, newName);
      await refreshProject([buildEntityRevisionKey("character", newName)]);
      useAppStore.getState().pushToast(
        `角色「${oldName}」→「${newName}」（更新 ${res.scripts_updated} 份劇本）`,
        "success",
      );
    } catch (err) {
      useAppStore.getState().pushToast(`改名失敗: ${(err as Error).message}`, "error");
    }
  }, [currentProjectName, refreshProject]);

  const handleRenameClue = useCallback(async (oldName: string, newName: string) => {
    if (!currentProjectName) return;
    try {
      const res = await API.renameClue(currentProjectName, oldName, newName);
      await refreshProject([buildEntityRevisionKey("clue", newName)]);
      useAppStore.getState().pushToast(
        `道具「${oldName}」→「${newName}」（更新 ${res.scripts_updated} 份劇本）`,
        "success",
      );
    } catch (err) {
      useAppStore.getState().pushToast(`改名失敗: ${(err as Error).message}`, "error");
    }
  }, [currentProjectName, refreshProject]);

  const handleAddClueSubmit = useCallback(async (
    name: string,
    description: string,
    importance: string,
    referenceFile?: File | null,
  ) => {
    if (!currentProjectName) return;
    try {
      await API.addClue(currentProjectName, name, description, importance);
      if (referenceFile) {
        await API.uploadFile(currentProjectName, "clue_ref", referenceFile, name);
      }
      await refreshProject();
      useAppStore.getState().pushToast(`道具「${name}」已新增`, "success");
    } catch (err) {
      useAppStore.getState().pushToast(`新增失敗: ${(err as Error).message}`, "error");
    }
  }, [currentProjectName, refreshProject]);

  const handleUploadClueReference = useCallback(
    async (name: string, file: File) => {
      if (!currentProjectName) return;
      try {
        await API.uploadFile(currentProjectName, "clue_ref", file, name);
        await refreshProject([buildEntityRevisionKey("clue", name)]);
        useAppStore.getState().pushToast(`道具「${name}」參考圖已上傳`, "success");
      } catch (err) {
        useAppStore
          .getState()
          .pushToast(`上傳參考圖失敗: ${(err as Error).message}`, "error");
      }
    },
    [currentProjectName, refreshProject],
  );

  const handleRemoveClueReference = useCallback(
    async (name: string) => {
      await removeReferenceImage(
        "clues",
        name,
        `道具「${name}」參考圖已移除`,
        [buildEntityRevisionKey("clue", name)],
      );
    },
    [removeReferenceImage],
  );

  // ---- Scene CRUD callbacks ----
  const handleSaveScene = useCallback(
    async (
      name: string,
      payload: { description: string; imageBackend?: string | null },
    ) => {
      if (!currentProjectName) return;
      try {
        await API.updateProjectScene(currentProjectName, name, {
          description: payload.description,
          image_backend: payload.imageBackend,
        });
        await refreshProject();
        useAppStore.getState().pushToast(`場景「${name}」已更新`, "success");
      } catch (err) {
        useAppStore
          .getState()
          .pushToast(`更新場景失敗: ${(err as Error).message}`, "error");
      }
    },
    [currentProjectName, refreshProject],
  );

  const handleUploadSceneReference = useCallback(
    async (name: string, file: File) => {
      if (!currentProjectName) return;
      try {
        await API.uploadFile(currentProjectName, "scene_ref", file, name);
        await refreshProject();
        useAppStore.getState().pushToast(`場景「${name}」參考圖已上傳`, "success");
      } catch (err) {
        useAppStore
          .getState()
          .pushToast(`上傳參考圖失敗: ${(err as Error).message}`, "error");
      }
    },
    [currentProjectName, refreshProject],
  );

  const handleRemoveSceneReference = useCallback(
    async (name: string) => {
      await removeReferenceImage("scenes", name, `場景「${name}」參考圖已移除`);
    },
    [removeReferenceImage],
  );

  const handleGenerateScene = useCallback(async (name: string) => {
    if (!currentProjectName) return;
    try {
      await API.generateScene(
        currentProjectName,
        name,
        currentProjectData?.scenes?.[name]?.description || name,
      );
      useAppStore
        .getState()
        .pushToast(`場景「${name}」生成任務已提交`, "success");
    } catch (err) {
      useAppStore.getState().pushToast(`提交失敗: ${(err as Error).message}`, "error");
    }
  }, [currentProjectName, currentProjectData]);

  const handleRenameScene = useCallback(async (oldName: string, newName: string) => {
    if (!currentProjectName) return;
    try {
      const res = await API.renameProjectScene(currentProjectName, oldName, newName);
      await refreshProject();
      useAppStore.getState().pushToast(
        `場景「${oldName}」→「${newName}」（更新 ${res.scripts_updated} 份劇本）`,
        "success",
      );
    } catch (err) {
      useAppStore.getState().pushToast(`改名失敗: ${(err as Error).message}`, "error");
    }
  }, [currentProjectName, refreshProject]);

  const handleDeleteScene = useCallback(
    async (name: string) => {
      if (!currentProjectName) return;
      try {
        await API.deleteProjectScene(currentProjectName, name);
        await refreshProject();
        useAppStore.getState().pushToast(`場景「${name}」已刪除`, "success");
      } catch (err) {
        useAppStore
          .getState()
          .pushToast(`刪除場景失敗: ${(err as Error).message}`, "error");
      }
    },
    [currentProjectName, refreshProject],
  );

  const handleAddSceneSubmit = useCallback(
    async (name: string, description: string, referenceFile?: File | null) => {
      if (!currentProjectName) return;
      try {
        await API.addProjectScene(currentProjectName, name, description);
        if (referenceFile) {
          await API.uploadFile(currentProjectName, "scene_ref", referenceFile, name);
        }
        await refreshProject();
        useAppStore.getState().pushToast(`場景「${name}」已新增`, "success");
      } catch (err) {
        useAppStore
          .getState()
          .pushToast(`新增場景失敗: ${(err as Error).message}`, "error");
      }
    },
    [currentProjectName, refreshProject],
  );

  const handleRestoreAsset = useCallback(async () => {
    await refreshProject();
  }, [refreshProject]);

  const [location] = useLocation();
  const lorebookMode = LOREBOOK_MODE_BY_ROUTE[location] ?? null;



  if (!currentProjectName) {
    return (
      <div className="flex h-full items-center justify-center text-gray-500">
        載入中...
      </div>
    );
  }

  return (
    <Switch>
      <Route path="/">
        <OverviewCanvas
          projectName={currentProjectName}
          projectData={currentProjectData}
        />
      </Route>

      <Route path="/lorebook">
        <Redirect to="/characters" />
      </Route>

      {/* Characters / Clues / Scenes share one LorebookGallery to avoid remount flash */}
      {lorebookMode && (
        <div className="p-4">
          <LorebookGallery
            projectName={currentProjectName}
            characters={currentProjectData?.characters ?? {}}
            clues={currentProjectData?.clues ?? {}}
            scenes={currentProjectData?.scenes ?? {}}
            mode={lorebookMode}
            onSaveCharacter={handleSaveCharacter}
            onUploadCharacterReference={handleUploadCharacterReference}
            onRemoveCharacterReference={handleRemoveCharacterReference}
            onUpdateClue={handleUpdateClue}
            onGenerateCharacter={handleGenerateCharacter}
            onGenerateClue={handleGenerateClue}
            onGenerateScene={handleGenerateScene}
            onUploadClueReference={handleUploadClueReference}
            onUploadSceneReference={handleUploadSceneReference}
            onRemoveClueReference={handleRemoveClueReference}
            onRemoveSceneReference={handleRemoveSceneReference}
            onDeleteCharacter={handleDeleteCharacter}
            onDeleteClue={handleDeleteClue}
            onRenameCharacter={handleRenameCharacter}
            onRenameClue={handleRenameClue}
            onRenameScene={handleRenameScene}
            onRestoreCharacterVersion={handleRestoreAsset}
            onRestoreClueVersion={handleRestoreAsset}
            generatingCharacterNames={generatingResources.characterNames}
            generatingClueNames={generatingResources.clueNames}
            generatingSceneNames={generatingResources.sceneNames}
            onSaveScene={handleSaveScene}
            onDeleteScene={handleDeleteScene}
            onRestoreSceneVersion={handleRestoreAsset}
            onAddCharacterSubmit={handleAddCharacterSubmit}
            onAddClueSubmit={handleAddClueSubmit}
            onAddSceneSubmit={handleAddSceneSubmit}
            onRefresh={refreshProject}
          />
        </div>
      )}

      <Route path="/source/:filename">
        {(params) => (
          <SourceFileViewer
            projectName={currentProjectName}
            filename={decodeURIComponent(params.filename)}
          />
        )}
      </Route>

      <Route path="/episodes/:episodeId">
        {(params) => {
          const epNum = parseInt(params.episodeId, 10);
          const episode = currentProjectData?.episodes?.find(
            (e) => e.episode === epNum,
          );
          const scriptFile = episode?.script_file?.replace(/^scripts\//, "");
          const script = scriptFile
            ? (currentScripts[scriptFile] ?? null)
            : null;

          const hasDraft = Boolean(episode);

          return (
            <TimelineCanvas
              key={epNum}
              projectName={currentProjectName}
              episode={epNum}
              episodeTitle={episode?.title}
              hasDraft={hasDraft}
              episodeScript={script}
              scriptFile={scriptFile ?? undefined}
              projectData={currentProjectData}
              videoBackend={currentProjectData?.video_backend}
              currentVideoResolution={currentVideoResolution}
              onUpdatePrompt={handleUpdatePrompt}
              onGenerateStoryboard={handleGenerateStoryboard}
              onGenerateVideo={handleGenerateVideo}
              onRestoreStoryboard={handleRestoreAsset}
              onRestoreVideo={handleRestoreAsset}
              generatingStoryboardIds={generatingResources.storyboardIds}
              generatingVideoIds={generatingResources.videoIds}
            />
          );
        }}
      </Route>
    </Switch>
  );
}
