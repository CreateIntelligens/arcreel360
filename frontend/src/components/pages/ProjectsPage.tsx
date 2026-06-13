import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation } from "wouter";
import { Loader2, Plus, FolderOpen, Upload, Settings } from "lucide-react";
import { API } from "@/api";
import { useProjectsStore } from "@/stores/projects-store";
import { useAppStore } from "@/stores/app-store";
import { useConfigStatusStore } from "@/stores/config-status-store";
import { CreateProjectModal } from "./CreateProjectModal";
import { OpenClawModal } from "./OpenClawModal";
import { ProjectCard } from "./projects/ProjectCard";
import { ImportConflictDialog } from "./projects/ImportConflictDialog";
import { DeleteProjectDialog } from "./projects/DeleteProjectDialog";
import {
  ImportDiagnosticsDialogWrapper,
  fallbackDiagnostics,
} from "./projects/ImportDiagnosticsDialog";
import type {
  ImportConflictPolicy,
  ImportFailureDiagnostics,
  ProjectSummary,
} from "@/types";

// ---------------------------------------------------------------------------
// ProjectsPage — project list with create button
// ---------------------------------------------------------------------------

export function ProjectsPage() {
  const [, navigate] = useLocation();
  const { projects, projectsLoading, showCreateModal, setProjects, setProjectsLoading, setShowCreateModal } =
    useProjectsStore();
  const [importingProject, setImportingProject] = useState(false);
  const [pendingImportFile, setPendingImportFile] = useState<File | null>(null);
  const [conflictProjectName, setConflictProjectName] = useState<string | null>(null);
  const [importDiagnostics, setImportDiagnostics] = useState<ImportFailureDiagnostics | null>(null);
  const [showOpenClaw, setShowOpenClaw] = useState(false);
  const [projectToDelete, setProjectToDelete] = useState<ProjectSummary | null>(null);
  const [deletingProject, setDeletingProject] = useState(false);
  const importInputRef = useRef<HTMLInputElement>(null);
  const isConfigComplete = useConfigStatusStore((s) => s.isComplete);
  const fetchConfigStatus = useConfigStatusStore((s) => s.fetch);

  const loadProjects = useCallback(async () => {
    setProjectsLoading(true);
    try {
      const res = await API.listProjects();
      setProjects(res.projects);
    } catch {
      // silently fail — user can retry
    } finally {
      setProjectsLoading(false);
    }
  }, [setProjects, setProjectsLoading]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      if (cancelled) return;
      await loadProjects();
    })();
    return () => {
      cancelled = true;
    };
  }, [loadProjects]);

  useEffect(() => {
    void fetchConfigStatus();
  }, [fetchConfigStatus]);

  const finishImport = useCallback(
    async (
      file: File,
      policy: ImportConflictPolicy,
      options?: { keepConflictDialog?: boolean },
    ) => {
      setImportingProject(true);
      try {
        const result = await API.importProject(file, policy);
        setPendingImportFile(null);
        setConflictProjectName(null);
        setImportDiagnostics(null);
        await loadProjects();

        const autoFixedCount = result.diagnostics.auto_fixed.length;
        const warningCount = result.diagnostics.warnings.length;
        useAppStore.getState().pushToast(
          autoFixedCount > 0
            ? `專案「${result.project.title || result.project_name}」已匯入，自動修復 ${autoFixedCount} 項`
            : `專案「${result.project.title || result.project_name}」已匯入`,
          "success"
        );
        if (warningCount > 0) {
          const warningMessages = result.diagnostics.warnings.map((w) => w.message).join("；");
          useAppStore.getState().pushToast(
            `匯入警告：${warningMessages}`,
            "warning"
          );
        }

        navigate(`/app/projects/${result.project_name}`);
      } catch (err) {
        const error = err as Error & {
          status?: number;
          detail?: string;
          errors?: string[];
          warnings?: string[];
          diagnostics?: ImportFailureDiagnostics;
          conflict_project_name?: string;
        };

        if (
          error.status === 409 &&
          error.conflict_project_name &&
          policy === "prompt"
        ) {
          setPendingImportFile(file);
          setConflictProjectName(error.conflict_project_name);
          return;
        }

        if (!options?.keepConflictDialog) {
          setPendingImportFile(null);
          setConflictProjectName(null);
        }

        const diagnostics = fallbackDiagnostics(error);
        setImportDiagnostics(diagnostics);
        const blockingCount = diagnostics.blocking.length;
        const autoFixableCount = diagnostics.auto_fixable.length;

        useAppStore
          .getState()
          .pushToast(
            `匯入失敗：${error.detail || error.message || "匯入失敗"}`
            + (blockingCount > 0 ? `（${blockingCount} 個阻斷問題` : "（0 個阻斷問題")
            + (autoFixableCount > 0 ? `，${autoFixableCount} 個可自動修復）` : "）"),
            "error"
          );
      } finally {
        setImportingProject(false);
      }
    },
    [loadProjects, navigate],
  );

  const handleImport = useCallback(
    async (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      event.target.value = "";
      if (!file || importingProject) return;

      setImportDiagnostics(null);
      await finishImport(file, "prompt");
    },
    [finishImport, importingProject],
  );

  const handleResolveConflict = useCallback(
    async (policy: Extract<ImportConflictPolicy, "rename" | "overwrite">) => {
      if (!pendingImportFile) return;
      await finishImport(pendingImportFile, policy, { keepConflictDialog: true });
    },
    [finishImport, pendingImportFile],
  );

  const handleCancelConflict = useCallback(() => {
    if (importingProject) return;
    setPendingImportFile(null);
    setConflictProjectName(null);
  }, [importingProject]);

  const handleConfirmDelete = useCallback(async () => {
    const project = projectToDelete;
    if (!project) return;

    setDeletingProject(true);
    try {
      await API.deleteProject(project.name);
      useAppStore
        .getState()
        .pushToast(`專案「${project.title || project.name}」已刪除`, "success");
      setProjectToDelete(null);
      await loadProjects();
    } catch (err) {
      const error = err as Error & { detail?: string };
      useAppStore
        .getState()
        .pushToast(`刪除失敗：${error.detail || error.message || "未知錯誤"}`, "error");
    } finally {
      setDeletingProject(false);
    }
  }, [projectToDelete, loadProjects]);

  const handleCancelDelete = useCallback(() => {
    if (deletingProject) return;
    setProjectToDelete(null);
  }, [deletingProject]);

  return (
    <div className="workbench-shell workbench-grid min-h-screen text-[color:var(--wb-text-primary)]">
      {/* Header */}
      <header className="relative border-b border-[color:var(--wb-border-soft)] px-6 py-5 backdrop-blur-xl">
        <div className="mx-auto flex max-w-6xl items-start justify-between gap-6">
          <div>
            <div className="workbench-kicker text-xs font-semibold">創作專案大廳</div>
            <h1 className="workbench-title mt-2 flex items-center gap-3 text-[1.9rem] font-semibold tracking-tight">
              <img src="/android-chrome-192x192.png" alt="ArcReel" className="h-8 w-8 rounded-xl" />
              <span>ArcReel 專案工作臺</span>
            </h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-[color:var(--wb-text-muted)]">
              在同一個入口管理小說轉影片專案、匯入封存與系統設定，優先突顯專案脈絡與創作進度，而不是後臺表單感。
            </p>
          </div>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => importInputRef.current?.click()}
              disabled={importingProject}
              className="workbench-button-secondary inline-flex items-center gap-1.5 rounded-xl px-4 py-2.5 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-60"
            >
              {importingProject ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Upload className="h-4 w-4" />
              )}
              {importingProject ? "匯入中..." : "匯入 ZIP"}
            </button>
            <button
              type="button"
              onClick={() => setShowCreateModal(true)}
              className="workbench-button-primary inline-flex cursor-pointer items-center gap-1.5 rounded-xl px-4 py-2.5 text-sm font-medium"
            >
              <Plus className="h-4 w-4" />
              新建專案
            </button>
            <div className="ml-1 flex items-center gap-1 border-l border-[color:var(--wb-border-soft)] pl-3">
              <button
                type="button"
                onClick={() => setShowOpenClaw(true)}
                className="workbench-button-secondary rounded-xl px-2.5 py-1.5 text-sm"
                title="OpenClaw 整合"
                aria-label="OpenClaw 整合指南"
              >
                🦞
              </button>
              <button
                type="button"
                onClick={() => navigate("/app/settings")}
                className="workbench-button-secondary relative rounded-xl p-2"
                title="系統設定"
                aria-label="系統設定"
              >
                <Settings className="h-4 w-4" />
                {!isConfigComplete && (
                  <span className="absolute right-0.5 top-0.5 h-2 w-2 rounded-full bg-rose-500" aria-label="設定不完整" />
                )}
              </button>
            </div>
          </div>
        </div>
        <input
          ref={importInputRef}
          type="file"
          accept=".zip,application/zip"
          onChange={handleImport}
          className="hidden"
        />
      </header>

      {/* Content */}
      <main className="relative mx-auto flex w-full max-w-6xl flex-col gap-6 px-6 py-8">
        <section className="workbench-panel-strong relative overflow-hidden rounded-[1.6rem] px-6 py-6">
          <div className="absolute inset-x-0 top-0 h-24 bg-gradient-to-r from-[rgba(109,140,255,0.16)] via-transparent to-[rgba(112,199,217,0.16)]" />
          <div className="relative grid gap-4 lg:grid-cols-[1.7fr_1fr]">
            <div>
              <div className="text-xs uppercase tracking-[0.22em] text-[color:var(--wb-accent-cyan)]">工作臺總覽</div>
              <h2 className="mt-2 text-2xl font-semibold text-[color:var(--wb-text-primary)]">從這裡進入每個創作專案</h2>
              <p className="mt-3 max-w-2xl text-sm leading-6 text-[color:var(--wb-text-muted)]">
                專案卡片現在優先顯示脈絡、進度與角色／道具完成度，讓入口頁更像創作工作臺總覽，而不是單純的資料清單。
              </p>
            </div>
            <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-1">
              <div className="rounded-2xl border border-white/6 bg-black/12 px-4 py-3">
                <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--wb-text-dim)]">專案總數</div>
                <div className="mt-2 text-2xl font-semibold text-[color:var(--wb-text-primary)]">{projects.length}</div>
              </div>
              <div className="rounded-2xl border border-white/6 bg-black/12 px-4 py-3">
                <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--wb-text-dim)]">設定狀態</div>
                <div className="mt-2 text-sm font-medium text-[color:var(--wb-text-secondary)]">{isConfigComplete ? "已就緒" : "待完善"}</div>
              </div>
              <div className="rounded-2xl border border-white/6 bg-black/12 px-4 py-3">
                <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--wb-text-dim)]">快速入口</div>
                <div className="mt-2 text-sm font-medium text-[color:var(--wb-text-secondary)]">匯入 ZIP / 新建專案 / 設定中心</div>
              </div>
            </div>
          </div>
        </section>

        {projectsLoading ? (
          <div className="workbench-panel flex items-center justify-center rounded-[1.4rem] py-20">
            <Loader2 className="h-6 w-6 animate-spin text-[color:var(--wb-accent)]" />
            <span className="ml-2 text-[color:var(--wb-text-muted)]">載入專案列表...</span>
          </div>
        ) : projects.length === 0 ? (
          <div className="workbench-panel flex flex-col items-center justify-center rounded-[1.4rem] py-20 text-[color:var(--wb-text-muted)]">
            <FolderOpen className="h-16 w-16 mb-4" />
            <p className="text-lg text-[color:var(--wb-text-primary)]">暫無專案</p>
            <p className="text-sm mt-1">點選右上角「新建專案」或「匯入 ZIP」開始創作</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {projects.map((p) => (
              <ProjectCard key={p.name} project={p} onRequestDelete={setProjectToDelete} />
            ))}
          </div>
        )}
      </main>

      {/* Create project modal */}
      {showCreateModal && <CreateProjectModal />}
      {conflictProjectName !== null && pendingImportFile !== null && (
        <ImportConflictDialog
          projectName={conflictProjectName}
          importing={importingProject}
          onCancel={handleCancelConflict}
          onConfirm={handleResolveConflict}
        />
      )}
      {importDiagnostics !== null && (
        <ImportDiagnosticsDialogWrapper
          diagnostics={importDiagnostics}
          onClose={() => setImportDiagnostics(null)}
        />
      )}
      {showOpenClaw && <OpenClawModal onClose={() => setShowOpenClaw(false)} />}
      {projectToDelete !== null && (
        <DeleteProjectDialog
          projectName={projectToDelete.name}
          projectTitle={projectToDelete.title}
          deleting={deletingProject}
          onCancel={handleCancelDelete}
          onConfirm={handleConfirmDelete}
        />
      )}
    </div>
  );
}
