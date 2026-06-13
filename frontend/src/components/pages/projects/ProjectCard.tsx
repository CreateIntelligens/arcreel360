import { useLocation } from "wouter";
import { FolderOpen, Trash2 } from "lucide-react";
import type { ProjectStatus, ProjectSummary } from "@/types";

const PHASE_LABELS: Record<string, string> = {
  setup: "專案概述",
  lorebook: "角色場景",
  scripting: "劇本創作",
  storyboard: "分鏡圖",
  video: "影片",
  completed: "已完成",
};

export function ProjectCard({
  project,
  onRequestDelete,
}: {
  project: ProjectSummary;
  onRequestDelete: (project: ProjectSummary) => void;
}) {
  const [, navigate] = useLocation();
  const projectPath = `/app/projects/${project.name}`;
  const projectLabel = project.title || project.name;
  const status = project.status;
  const hasStatus = status && "current_phase" in status;

  const pct = hasStatus ? Math.round((status as ProjectStatus).phase_progress * 100) : 0;
  const phase = hasStatus ? (status as ProjectStatus).current_phase : "";
  const phaseLabel = PHASE_LABELS[phase] ?? phase;
  const characters = hasStatus ? (status as ProjectStatus).characters : null;
  const clues = hasStatus ? (status as ProjectStatus).clues : null;
  const scenes = hasStatus ? (status as ProjectStatus).scenes : null;
  const summary = hasStatus ? (status as ProjectStatus).episodes_summary : null;

  const openProject = () => navigate(projectPath);

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={openProject}
      onKeyDown={(e) => {
        if (e.currentTarget !== e.target) return;
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          openProject();
        }
      }}
      className="project-card workbench-panel hover:workbench-panel-strong group relative flex cursor-pointer flex-col gap-4 overflow-hidden rounded-[1.35rem] p-5 text-left"
    >
      <div className="pointer-events-none absolute inset-x-0 top-0 h-24 bg-gradient-to-b from-white/6 to-transparent opacity-70" />

      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          onRequestDelete(project);
        }}
        className="absolute right-3 top-3 z-20 flex h-8 w-8 items-center justify-center rounded-lg border border-white/10 bg-black/50 text-[color:var(--wb-text-muted)] opacity-0 transition hover:border-rose-400/50 hover:text-rose-400 group-hover:opacity-100"
        title="刪除專案"
        aria-label={`刪除專案 ${projectLabel}`}
      >
        <Trash2 className="h-4 w-4" />
      </button>

      {/* Thumbnail or placeholder */}
      <div className="relative aspect-video w-full overflow-hidden rounded-[1rem] border border-white/6 bg-[rgba(10,16,28,0.86)]">
        {project.thumbnail ? (
          <img
            src={project.thumbnail}
            alt={projectLabel}
            className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.03]"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-[color:var(--wb-text-dim)]">
            <FolderOpen className="h-10 w-10" />
          </div>
        )}
        <div className="absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-black/35 to-transparent" />
      </div>

      {/* Info */}
      <div className="relative z-10">
        <div className="text-[11px] uppercase tracking-[0.24em] text-[color:var(--wb-accent-cyan)]">
          創作工作臺
        </div>
        <h3 className="mt-2 truncate text-base font-semibold text-[color:var(--wb-text-primary)]">
          {projectLabel}
        </h3>
        <p className="mt-1 text-xs text-[color:var(--wb-text-muted)]">
          {project.style || "未設定風格"}
          {phaseLabel ? ` · ${phaseLabel}` : ""}
        </p>
      </div>

      {/* Progress bar */}
      <div className="rounded-2xl border border-white/6 bg-black/12 px-3 py-3">
        <div className="mb-2 flex justify-between text-[11px] uppercase tracking-[0.18em] text-[color:var(--wb-text-dim)]">
          <span>{phaseLabel || "進度"}</span>
          <span>{pct}%</span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-[rgba(129,146,181,0.16)]">
          <div
            className="h-full rounded-full bg-[linear-gradient(90deg,var(--wb-accent),var(--wb-accent-cyan))] transition-all"
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>

      {/* Characters, Clues & Scenes — always shown */}
      {(characters || clues || scenes) && (
        <div className="flex flex-wrap gap-2 text-xs text-[color:var(--wb-text-muted)]">
          {characters && (
            <span className="rounded-full border border-white/6 bg-black/12 px-2.5 py-1">角色 {characters.completed}/{characters.total}</span>
          )}
          {clues && (
            <span className="rounded-full border border-white/6 bg-black/12 px-2.5 py-1">道具 {clues.completed}/{clues.total}</span>
          )}
          {scenes && (
            <span className="rounded-full border border-white/6 bg-black/12 px-2.5 py-1">場景 {scenes.completed}/{scenes.total}</span>
          )}
        </div>
      )}

      {/* Episodes summary */}
      {summary && summary.total > 0 && (
        <div className="text-xs leading-6 text-[color:var(--wb-text-muted)]">
          {summary.total} 集
          {summary.scripted > 0 && ` · ${summary.scripted} 集劇本完成`}
          {summary.in_production > 0 && ` · ${summary.in_production} 集製作中`}
          {summary.completed > 0 && ` · ${summary.completed} 集已完成`}
        </div>
      )}
    </div>
  );
}
