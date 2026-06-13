import { useState, useEffect, useMemo } from "react";
import { User, Puzzle, Mountain, Plus, type LucideIcon } from "lucide-react";
import { useLocation } from "wouter";
import { API } from "@/api";
import { CharacterCard } from "./CharacterCard";
import { ClueCard } from "./ClueCard";
import { SceneCard } from "./SceneCard";
import { AddCharacterForm } from "./AddCharacterForm";
import { AddClueForm } from "./AddClueForm";
import { AddSceneForm } from "./AddSceneForm";
import { LorebookAIExtractModal } from "./LorebookAIExtractModal";
import { useScrollTarget } from "@/hooks/useScrollTarget";
import { useConfirm } from "@/hooks/useConfirm";
import { useAppStore } from "@/stores/app-store";
import type { Character, Clue, Scene, ProviderInfo } from "@/types";
import { providersApi } from "@/api/providers";
import { buildMediaModelOptions } from "@/utils/provider-models";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface LorebookGalleryProps {
  projectName: string;
  characters: Record<string, Character>;
  clues: Record<string, Clue>;
  /** 舊專案可能沒有 scenes，預設視為空 */
  scenes?: Record<string, Scene>;
  /** When specified, only show the given section without tab bar. */
  mode?: "characters" | "clues" | "scenes";
  onSaveCharacter: (
    name: string,
    payload: {
      description: string;
      voiceStyle: string;
      imageBackend?: string | null;
    }
  ) => Promise<void>;
  onUploadCharacterReference: (name: string, file: File) => Promise<void> | void;
  onRemoveCharacterReference?: (name: string) => Promise<void> | void;
  onUpdateClue: (name: string, updates: Partial<Clue>) => Promise<void>;
  onGenerateCharacter: (name: string) => void;
  onGenerateClue: (name: string) => void;
  onGenerateScene: (name: string) => void;
  onUploadClueReference?: (name: string, file: File) => Promise<void> | void;
  onUploadSceneReference?: (name: string, file: File) => Promise<void> | void;
  onRemoveClueReference?: (name: string) => Promise<void> | void;
  onRemoveSceneReference?: (name: string) => Promise<void> | void;
  onDeleteCharacter?: (name: string) => Promise<void> | void;
  onDeleteClue?: (name: string) => Promise<void> | void;
  onRenameCharacter?: (oldName: string, newName: string) => Promise<void> | void;
  onRenameClue?: (oldName: string, newName: string) => Promise<void> | void;
  onRenameScene?: (oldName: string, newName: string) => Promise<void> | void;
  onRestoreCharacterVersion?: () => Promise<void> | void;
  onRestoreClueVersion?: () => Promise<void> | void;
  generatingCharacterNames?: Set<string>;
  generatingClueNames?: Set<string>;
  generatingSceneNames?: Set<string>;
  /** ---- Scene 相關 ---- */
  onSaveScene: (
    name: string,
    payload: {
      description: string;
      imageBackend?: string | null;
    },
  ) => Promise<void>;
  onDeleteScene?: (name: string) => Promise<void> | void;
  onRestoreSceneVersion?: () => Promise<void> | void;
  onAddCharacterSubmit: (
    name: string,
    description: string,
    voiceStyle: string,
    referenceFile?: File | null,
  ) => Promise<void>;
  onAddClueSubmit: (
    name: string,
    description: string,
    importance: "major" | "minor",
    referenceFile?: File | null,
  ) => Promise<void>;
  onAddSceneSubmit: (
    name: string,
    description: string,
    referenceFile?: File | null,
  ) => Promise<void>;
  /** AI 批次匯入後，通知父元件重新獲取資料 */
  onRefresh?: () => Promise<void> | void;
}

// ---------------------------------------------------------------------------
// Tab type
// ---------------------------------------------------------------------------

type Tab = "characters" | "clues" | "scenes";
type BatchKind = "characters" | "clues" | "scenes";

const BATCH_LABELS: Record<BatchKind, string> = {
  characters: "角色",
  clues: "道具",
  scenes: "場景",
};

const TAB_ORDER: Tab[] = ["characters", "clues", "scenes"];
const TAB_ICONS: Record<Tab, LucideIcon> = {
  characters: User,
  clues: Puzzle,
  scenes: Mountain,
};

// ---------------------------------------------------------------------------
// LorebookGallery
// ---------------------------------------------------------------------------

export function LorebookGallery({
  projectName,
  characters,
  clues,
  scenes,
  mode,
  onSaveCharacter,
  onUploadCharacterReference,
  onRemoveCharacterReference,
  onUpdateClue,
  onGenerateCharacter,
  onGenerateClue,
  onGenerateScene,
  onUploadClueReference,
  onUploadSceneReference,
  onRemoveClueReference,
  onRemoveSceneReference,
  onDeleteCharacter,
  onDeleteClue,
  onRenameCharacter,
  onRenameClue,
  onRenameScene,
  onRestoreCharacterVersion,
  onRestoreClueVersion,
  generatingCharacterNames,
  generatingClueNames,
  generatingSceneNames,
  onSaveScene,
  onDeleteScene,
  onRestoreSceneVersion,
  onAddCharacterSubmit,
  onAddClueSubmit,
  onAddSceneSubmit,
  onRefresh,
}: LorebookGalleryProps) {
  const [addingCharacter, setAddingCharacter] = useState(false);
  const [addingClue, setAddingClue] = useState(false);
  const [addingScene, setAddingScene] = useState(false);
  const confirm = useConfirm();
  const [location, setLocation] = useLocation();
  const assistantPanelOpen = useAppStore((s) => s.assistantPanelOpen);

  const activeTab = useMemo<Tab>(() => {
    if (mode) return mode;
    const match = location.match(/^\/(characters|clues|scenes)/);
    return (match ? match[1] : "characters") as Tab;
  }, [mode, location]);

  const handleTabChange = (tab: Tab) => {
    setLocation(`/${tab}`);
  };

  const [extractingType, setExtractingType] = useState<"character" | "clue" | "scene" | null>(null);

  const [providers, setProviders] = useState<ProviderInfo[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    providersApi
      .getProviders()
      .then((res) => {
        if (!cancelled) setProviders(res.providers);
      })
      .catch((err) => {
        console.error("Failed to load providers in LorebookGallery:", err);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const modelOptions = useMemo(() => buildMediaModelOptions(providers), [providers]);

  const gridClassName = useMemo(() => {
    return assistantPanelOpen
      ? "grid grid-cols-1 lg:grid-cols-2 gap-4"
      : "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4";
  }, [assistantPanelOpen]);

  // Respond to agent-triggered scroll targets
  useScrollTarget("character");
  useScrollTarget("clue");

  const scrollTarget = useAppStore((s) => s.scrollTarget);
  useEffect(() => {
    if (!scrollTarget) return;
    if (scrollTarget.type === "character") {
      setLocation("/characters");
      setTimeout(() => {
        const el = document.getElementById(`character-${scrollTarget.id}`);
        el?.scrollIntoView({ behavior: "smooth", block: "center" });
      }, 100);
    } else if (scrollTarget.type === "clue") {
      setLocation("/clues");
      setTimeout(() => {
        const el = document.getElementById(`clue-${scrollTarget.id}`);
        el?.scrollIntoView({ behavior: "smooth", block: "center" });
      }, 100);
    }
  }, [scrollTarget, setLocation]);

  const charEntries = Object.entries(characters);
  const clueEntries = Object.entries(clues);
  const sceneEntries = Object.entries(scenes ?? {});
  const charCount = charEntries.length;
  const clueCount = clueEntries.length;
  const sceneCount = sceneEntries.length;

  const [batchBusy, setBatchBusy] = useState<BatchKind | null>(null);

  const runBatch = async (kind: BatchKind, force: boolean) => {
    if (batchBusy) return;
    setBatchBusy(kind);
    try {
      let res: { enqueued: string[]; skipped: { id: string; reason: string }[] };
      if (kind === "characters") {
        res = await API.batchGenerateCharacters(projectName, { force });
      } else if (kind === "clues") {
        res = await API.batchGenerateClues(projectName, { force });
      } else {
        res = await API.batchGenerateScenes(projectName, { force });
      }
      useAppStore.getState().pushToast(
        `已入隊 ${res.enqueued.length} 個${BATCH_LABELS[kind]}，略過 ${res.skipped.length}`,
        "success",
      );
    } catch (err) {
      useAppStore.getState().pushToast(
        `批次生成${BATCH_LABELS[kind]}失敗：${(err as Error).message}`,
        "error",
      );
    } finally {
      setBatchBusy(null);
    }
  };

  const isGeneratingCharacter = (name: string) =>
    generatingCharacterNames?.has(name) ?? false;
  const isGeneratingClue = (name: string) =>
    generatingClueNames?.has(name) ?? false;
  const isGeneratingScene = (name: string) =>
    generatingSceneNames?.has(name) ?? false;

  const showTabs = mode === "characters" || mode === "clues" || mode === "scenes" || !mode;
  const tabCounts: Record<Tab, number> = {
    characters: charCount,
    clues: clueCount,
    scenes: sceneCount,
  };

  return (
    <div className="flex flex-col gap-6">
      {showTabs && (
        <div className="flex border-b border-gray-800 pb-2 mb-2 gap-2">
          {TAB_ORDER.map((tab) => {
            const isActive = activeTab === tab;
            const label = BATCH_LABELS[tab];
            const count = tabCounts[tab];
            const Icon = TAB_ICONS[tab];

            return (
              <button
                key={tab}
                type="button"
                onClick={() => handleTabChange(tab)}
                className={`flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg transition-all duration-200 focus-ring ${
                  isActive
                    ? "bg-indigo-600/10 border border-indigo-500/30 text-indigo-400 font-bold shadow-md shadow-indigo-500/5"
                    : "text-gray-400 hover:bg-gray-800/50 hover:text-gray-200 border border-transparent"
                }`}
              >
                <Icon className={`h-4 w-4 ${isActive ? "text-indigo-400" : "text-gray-500"}`} />
                <span>{label}</span>
                <span className={`px-1.5 py-0.5 text-xs rounded-full ${
                  isActive ? "bg-indigo-500/20 text-indigo-300" : "bg-gray-800 text-gray-500"
                }`}>
                  {count}
                </span>
              </button>
            );
          })}
        </div>
      )}

      {/* ---- Characters Section ---- */}
      {activeTab === "characters" && (
        <div className="p-4 flex flex-col gap-4 bg-gray-900/10 border border-gray-800/40 rounded-xl">
          {charCount === 0 ? (
            <div className="flex flex-col items-center justify-center gap-4 py-12">
              <EmptyState
                icon={<User className="h-12 w-12 text-gray-600" />}
                message="暫無角色，點選下方按鈕新增"
              />
              <div className="flex gap-2">
                <AddButton onClick={() => setAddingCharacter(true)} className="mx-0">新增角色</AddButton>
                <button
                  type="button"
                  onClick={() => setExtractingType("character")}
                  className="flex items-center gap-1.5 rounded-lg border border-gray-700 bg-gray-800/40 px-4 py-2 text-sm font-medium text-gray-400 hover:border-gray-500 hover:text-gray-200 transition-colors focus:outline-none"
                >
                  根據原文匯入角色
                </button>
              </div>
              {addingCharacter && (
                <div className="w-full max-w-md mt-4 text-left">
                  <AddCharacterForm
                    onSubmit={async (name, desc, voice, refFile) => {
                      await onAddCharacterSubmit(name, desc, voice, refFile);
                      setAddingCharacter(false);
                    }}
                    onCancel={() => setAddingCharacter(false)}
                  />
                </div>
              )}
            </div>
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-2 mb-2">
                <AddButton onClick={() => setAddingCharacter(true)} className="mx-0">新增角色</AddButton>
                <button
                  type="button"
                  onClick={() => setExtractingType("character")}
                  className="flex items-center gap-1.5 rounded-lg border border-gray-700 bg-gray-800/40 px-4 py-2 text-sm font-medium text-gray-400 hover:border-gray-500 hover:text-gray-200 transition-colors focus:outline-none"
                >
                  根據原文匯入角色
                </button>
                <BatchButton
                  loading={batchBusy === "characters"}
                  disabled={batchBusy !== null}
                  onClick={() => void runBatch("characters", false)}
                >
                  批次生成（缺圖）
                </BatchButton>
              </div>
              <div className={gridClassName}>
                {charEntries.map(([charName, character]) => (
                  <div id={`character-${charName}`} key={charName}>
                    <CharacterCard
                      name={charName}
                      character={character}
                      projectName={projectName}
                      onSave={onSaveCharacter}
                      onUploadReference={onUploadCharacterReference}
                      onRemoveReference={onRemoveCharacterReference}
                      onGenerate={onGenerateCharacter}
                      onDelete={onDeleteCharacter}
                      onRename={onRenameCharacter}
                      onRestoreVersion={onRestoreCharacterVersion}
                      generating={isGeneratingCharacter(charName)}
                      modelOptions={modelOptions}
                    />
                  </div>
                ))}
                {addingCharacter && (
                  <AddCharacterForm
                    onSubmit={async (name, desc, voice, refFile) => {
                      await onAddCharacterSubmit(name, desc, voice, refFile);
                      setAddingCharacter(false);
                    }}
                    onCancel={() => setAddingCharacter(false)}
                  />
                )}
              </div>
            </>
          )}
        </div>
      )}

      {/* ---- Clues Section ---- */}
      {activeTab === "clues" && (
        <div className="p-4 flex flex-col gap-4 bg-gray-900/10 border border-gray-800/40 rounded-xl">
          {clueCount === 0 ? (
            <div className="flex flex-col items-center justify-center gap-4 py-12">
              <EmptyState
                icon={<Puzzle className="h-12 w-12 text-gray-600" />}
                message="暫無道具，點選下方按鈕新增"
              />
              <div className="flex gap-2">
                <AddButton onClick={() => setAddingClue(true)} className="mx-0">新增道具</AddButton>
                <button
                  type="button"
                  onClick={() => setExtractingType("clue")}
                  className="flex items-center gap-1.5 rounded-lg border border-gray-700 bg-gray-800/40 px-4 py-2 text-sm font-medium text-gray-400 hover:border-gray-500 hover:text-gray-200 transition-colors focus:outline-none"
                >
                  根據原文匯入道具
                </button>
              </div>
              {addingClue && (
                <div className="w-full max-w-md mt-4 text-left">
                  <AddClueForm
                    onSubmit={async (name, desc, importance, refFile) => {
                      await onAddClueSubmit(name, desc, importance, refFile);
                      setAddingClue(false);
                    }}
                    onCancel={() => setAddingClue(false)}
                  />
                </div>
              )}
            </div>
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-2 mb-2">
                <AddButton onClick={() => setAddingClue(true)} className="mx-0">新增道具</AddButton>
                <button
                  type="button"
                  onClick={() => setExtractingType("clue")}
                  className="flex items-center gap-1.5 rounded-lg border border-gray-700 bg-gray-800/40 px-4 py-2 text-sm font-medium text-gray-400 hover:border-gray-500 hover:text-gray-200 transition-colors focus:outline-none"
                >
                  根據原文匯入道具
                </button>
                <BatchButton
                  loading={batchBusy === "clues"}
                  disabled={batchBusy !== null}
                  onClick={() => void runBatch("clues", false)}
                >
                  批次生成（缺圖）
                </BatchButton>
              </div>
              <div className={gridClassName}>
                {clueEntries.map(([clueName, clue]) => (
                  <div id={`clue-${clueName}`} key={clueName}>
                    <ClueCard
                      name={clueName}
                      clue={clue}
                      projectName={projectName}
                      onSave={(n, payload) =>
                        onUpdateClue(n, {
                          description: payload.description,
                          image_backend: payload.imageBackend,
                        })
                      }
                      onGenerate={onGenerateClue}
                      onUploadReference={onUploadClueReference}
                      onRemoveReference={onRemoveClueReference}
                      onDelete={onDeleteClue}
                      onRename={onRenameClue}
                      onRestoreVersion={onRestoreClueVersion}
                      generating={isGeneratingClue(clueName)}
                      modelOptions={modelOptions}
                    />
                  </div>
                ))}
                {addingClue && (
                  <AddClueForm
                    onSubmit={async (name, desc, importance, refFile) => {
                      await onAddClueSubmit(name, desc, importance, refFile);
                      setAddingClue(false);
                    }}
                    onCancel={() => setAddingClue(false)}
                  />
                )}
              </div>
            </>
          )}
        </div>
      )}

      {/* ---- Scenes Section ---- */}
      {activeTab === "scenes" && (
        <div className="p-4 flex flex-col gap-4 bg-gray-900/10 border border-gray-800/40 rounded-xl">
          {sceneCount === 0 ? (
            <div className="flex flex-col items-center justify-center gap-4 py-12">
              <EmptyState
                icon={<Mountain className="h-12 w-12 text-gray-600" />}
                message="暫無場景，點選下方按鈕新增"
              />
              <div className="flex gap-2">
                <AddButton onClick={() => setAddingScene(true)} className="mx-0">新增場景</AddButton>
                <button
                  type="button"
                  onClick={() => setExtractingType("scene")}
                  className="flex items-center gap-1.5 rounded-lg border border-gray-700 bg-gray-800/40 px-4 py-2 text-sm font-medium text-gray-400 hover:border-gray-500 hover:text-gray-200 transition-colors focus:outline-none"
                >
                  根據原文匯入場景
                </button>
              </div>
              {addingScene && (
                <div className="w-full max-w-md mt-4 text-left">
                  <AddSceneForm
                    onSubmit={async (name, desc, refFile) => {
                      await onAddSceneSubmit(name, desc, refFile);
                      setAddingScene(false);
                    }}
                    onCancel={() => setAddingScene(false)}
                  />
                </div>
              )}
            </div>
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-2 mb-2">
                <AddButton onClick={() => setAddingScene(true)} className="mx-0">新增場景</AddButton>
                <button
                  type="button"
                  onClick={() => setExtractingType("scene")}
                  className="flex items-center gap-1.5 rounded-lg border border-gray-700 bg-gray-800/40 px-4 py-2 text-sm font-medium text-gray-400 hover:border-gray-500 hover:text-gray-200 transition-colors focus:outline-none"
                >
                  根據原文匯入場景
                </button>
                <BatchButton
                  loading={batchBusy === "scenes"}
                  disabled={batchBusy !== null}
                  onClick={() => void runBatch("scenes", false)}
                >
                  批次生成（缺圖）
                </BatchButton>
              </div>
              <div className={gridClassName}>
                {sceneEntries.map(([sceneName, scene]) => (
                  <div id={`scene-${sceneName}`} key={sceneName}>
                    <SceneCard
                      name={sceneName}
                      scene={scene}
                      projectName={projectName}
                      onSave={onSaveScene}
                      onGenerate={onGenerateScene}
                      onUploadReference={onUploadSceneReference}
                      onRemoveReference={onRemoveSceneReference}
                      onDelete={onDeleteScene}
                      onRename={onRenameScene}
                      onRestoreVersion={onRestoreSceneVersion}
                      generating={isGeneratingScene(sceneName)}
                      modelOptions={modelOptions}
                    />
                  </div>
                ))}
                {addingScene && (
                  <AddSceneForm
                    onSubmit={async (name, desc, refFile) => {
                      await onAddSceneSubmit(name, desc, refFile);
                      setAddingScene(false);
                    }}
                    onCancel={() => setAddingScene(false)}
                  />
                )}
              </div>
            </>
          )}
        </div>
      )}

      <LorebookAIExtractModal
        isOpen={extractingType !== null}
        onClose={() => setExtractingType(null)}
        projectName={projectName}
        entityType={extractingType ?? "character"}
        modelOptions={modelOptions}
        onImported={() => { void onRefresh?.(); }}
      />
    </div>
  );
}

function BatchButton({
  onClick,
  children,
  loading,
  disabled,
  variant = "primary",
}: {
  onClick: () => void;
  children: React.ReactNode;
  loading?: boolean;
  disabled?: boolean;
  variant?: "primary" | "warning";
}) {
  const cls =
    variant === "warning"
      ? "bg-amber-600 hover:bg-amber-500 text-white border-none shadow-md shadow-amber-500/5"
      : "bg-indigo-600 hover:bg-indigo-500 text-white border-none shadow-md shadow-indigo-500/5";
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-medium transition-all disabled:cursor-not-allowed disabled:opacity-50 ${cls}`}
    >
      {loading && (
        <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border border-current border-t-transparent" />
      )}
      {children}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Internal sub-components
// ---------------------------------------------------------------------------

function EmptyState({
  icon,
  message,
}: {
  icon: React.ReactNode;
  message: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-gray-500">
      {icon}
      <p className="text-sm">{message}</p>
    </div>
  );
}

function AddButton({
  onClick,
  children,
  className = "mx-auto",
}: {
  onClick: () => void;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex items-center gap-1.5 rounded-lg border border-gray-700 px-4 py-2 text-sm font-medium text-gray-400 hover:border-gray-500 hover:text-gray-200 transition-colors ${className}`}
    >
      <Plus className="h-4 w-4" />
      {children}
    </button>
  );
}
