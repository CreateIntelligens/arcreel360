import { startTransition, useState, useEffect, useRef } from "react";
import { useLocation } from "wouter";
import { ChevronLeft, Activity, Settings, Bell, Download, Loader2 } from "lucide-react";
import { useAppStore } from "@/stores/app-store";
import { useConfigStatusStore } from "@/stores/config-status-store";
import { useProjectsStore } from "@/stores/projects-store";
import { useTasksStore } from "@/stores/tasks-store";
import { useUsageStore, type UsageStats } from "@/stores/usage-store";
import { TaskHud } from "@/components/task-hud/TaskHud";
import { UsageDrawer } from "./UsageDrawer";
import { WorkspaceNotificationsDrawer } from "./WorkspaceNotificationsDrawer";
import { ExportScopeDialog } from "./ExportScopeDialog";

import { API } from "@/api";
import { ArchiveDiagnosticsDialog } from "@/components/shared/ArchiveDiagnosticsDialog";
import type { ExportDiagnostics, WorkspaceNotification } from "@/types";
import { sortEpisodesForDisplay } from "@/utils/episodes";

/** 透過隱藏 <a> 觸發瀏覽器下載，避免 window.open 產生空白標籤頁 */
function triggerBrowserDownload(url: string) {
  const a = document.createElement("a");
  a.href = url;
  a.style.display = "none";
  document.body.appendChild(a);
  a.click();
  a.remove();
}

// ---------------------------------------------------------------------------
// Phase definitions
// ---------------------------------------------------------------------------

const PHASES = [
  { key: "setup", label: "專案概述" },
  { key: "lorebook", label: "角色場景" },
  { key: "scripting", label: "劇本創作" },
  { key: "storyboard", label: "分鏡圖" },
  { key: "video", label: "影片" },
  { key: "completed", label: "已完成" },
] as const;

type PhaseKey = (typeof PHASES)[number]["key"];

// ---------------------------------------------------------------------------
// PhaseStepper — horizontal workflow indicator
// ---------------------------------------------------------------------------

function PhaseStepper({
  currentPhase,
  onNavigate,
}: {
  currentPhase: string | undefined;
  onNavigate: (phase: PhaseKey) => void;
}) {
  const currentIdx = PHASES.findIndex((p) => p.key === currentPhase);

  return (
    <nav className="flex items-center gap-1" aria-label="工作流階段">
      {PHASES.map((phase, idx) => {
        const isCompleted = currentIdx > idx;
        const isCurrent = currentIdx === idx;

        // Determine colors
        let circleClass =
          "flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-[10px] font-semibold transition-colors";
        let labelClass = "text-xs whitespace-nowrap transition-colors";

        if (isCompleted) {
          circleClass += " border-transparent bg-[color:var(--wb-success)] text-slate-950";
          labelClass += " text-[color:var(--wb-success)]";
        } else if (isCurrent) {
          circleClass += " border-[rgba(136,163,255,0.32)] bg-[color:var(--wb-accent)] text-slate-950";
          labelClass += " font-medium text-[color:var(--wb-text-primary)]";
        } else {
          circleClass += " border-[color:var(--wb-border-soft)] bg-[rgba(15,22,36,0.84)] text-[color:var(--wb-text-dim)]";
          labelClass += " text-[color:var(--wb-text-dim)]";
        }

        return (
          <div key={phase.key} className="flex items-center gap-1">
            {/* Connector line (before each step except the first) */}
            {idx > 0 && (
              <div
                className={`h-px w-4 shrink-0 ${isCompleted ? "bg-[color:var(--wb-success)]" : "bg-[color:var(--wb-border-soft)]"
                  }`}
              />
            )}

            {/* Step circle + label — 點擊跳到該階段對應工作區 */}
            <button
              type="button"
              onClick={() => onNavigate(phase.key)}
              aria-current={isCurrent ? "step" : undefined}
              title={`前往「${phase.label}」`}
              className="flex items-center gap-1.5 rounded px-1 py-0.5 transition-colors hover:bg-[rgba(136,163,255,0.12)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[color:var(--wb-accent)]"
            >
              <span className={circleClass}>{idx + 1}</span>
              <span className={labelClass}>{phase.label}</span>
            </button>
          </div>
        );
      })}
    </nav>
  );
}

// ---------------------------------------------------------------------------
// GlobalHeader
// ---------------------------------------------------------------------------

interface GlobalHeaderProps {
  onNavigateBack?: () => void;
}

export function GlobalHeader({ onNavigateBack }: GlobalHeaderProps) {
  const [, setLocation] = useLocation();
  const { currentProjectData, currentProjectName } = useProjectsStore();
  const { stats } = useTasksStore();
  const { taskHudOpen, setTaskHudOpen, triggerScrollTo, markWorkspaceNotificationRead } =
    useAppStore();
  const { stats: usageStats, setStats: setUsageStats } = useUsageStore();
  const [usageDrawerOpen, setUsageDrawerOpen] = useState(false);
  const [notificationDrawerOpen, setNotificationDrawerOpen] = useState(false);
  const [exportingProject, setExportingProject] = useState(false);
  const [exportDialogOpen, setExportDialogOpen] = useState(false);
  const [jianyingExporting, setJianyingExporting] = useState(false);
  const [exportDiagnostics, setExportDiagnostics] = useState<ExportDiagnostics | null>(null);
  const usageAnchorRef = useRef<HTMLDivElement>(null);
  const notificationAnchorRef = useRef<HTMLDivElement>(null);
  const taskHudAnchorRef = useRef<HTMLDivElement>(null);
  const exportAnchorRef = useRef<HTMLDivElement>(null);
  const isConfigComplete = useConfigStatusStore((s) => s.isComplete);
  const fetchConfigStatus = useConfigStatusStore((s) => s.fetch);
  const workspaceNotifications = useAppStore((s) => s.workspaceNotifications);

  const currentPhase = currentProjectData?.status?.current_phase;
  const contentMode = currentProjectData?.content_mode;
  const runningCount = stats.running + stats.queued;
  const displayProjectTitle =
    currentProjectData?.title?.trim() || currentProjectName || "未選擇專案";
  const unreadNotificationCount = workspaceNotifications.filter((item) => !item.read).length;

  // 載入費用統計資料（任務完成時自動重新整理）
  const completedTaskCount = stats.succeeded + stats.failed;
  useEffect(() => {
    API.getUsageStats(currentProjectName ? { projectName: currentProjectName } : {})
      .then((res) => {
        setUsageStats(res as unknown as UsageStats);
      })
      .catch(() => { });
  }, [currentProjectName, completedTaskCount, setUsageStats]);

  useEffect(() => {
    void fetchConfigStatus();
  }, [fetchConfigStatus]);


  // Format content mode badge text
  const modeBadgeText =
    contentMode === "drama" ? "劇本動畫 16:9" : "說書模式 9:16";

  // Format cost display – show multi-currency summary
  const costByCurrency = usageStats?.cost_by_currency ?? {};
  const costText = Object.entries(costByCurrency)
    .filter(([, v]) => v > 0)
    .map(([currency, amount]) => `${currency === "CNY" ? "¥" : "$"}${amount.toFixed(2)}`)
    .join(" + ") || "$0.00";

  const handlePhaseNavigate = (phase: PhaseKey) => {
    // lorebook 跳到全域圖鑑頁，scripting / storyboard / video 為集內階段，跳到第一集工作區；其餘跳全域頁
    const firstEpisode = sortEpisodesForDisplay(currentProjectData?.episodes ?? [])[0];
    let route: string;
    if (phase === "lorebook") {
      route = "/lorebook";
    } else if (phase === "scripting") {
      route = firstEpisode ? `/episodes/${firstEpisode.episode}` : "/";
    } else if (phase === "storyboard" || phase === "video") {
      route = firstEpisode ? `/episodes/${firstEpisode.episode}?tab=${phase}` : "/";
    } else {
      route = "/";
    }
    startTransition(() => {
      setLocation(route);
    });
  };

  const handleNotificationNavigate = (notification: WorkspaceNotification) => {
    if (!notification.target) return;
    const target = notification.target;

    markWorkspaceNotificationRead(notification.id);
    setNotificationDrawerOpen(false);
    startTransition(() => {
      setLocation(target.route);
    });
    triggerScrollTo({
      type: target.type,
      id: target.id,
      route: target.route,
      highlight_style: target.highlight_style ?? "flash",
      expires_at: Date.now() + 3000,
    });
  };

  const handleJianyingExport = async (episode: number, draftPath: string, jianyingVersion: string) => {
    if (!currentProjectName || jianyingExporting) return;

    setJianyingExporting(true);
    try {
      const { download_token } = await API.requestExportToken(currentProjectName, "current");
      const url = API.getJianyingDraftDownloadUrl(
        currentProjectName, episode, draftPath, download_token, jianyingVersion,
      );
      triggerBrowserDownload(url);
      setExportDialogOpen(false);
      useAppStore.getState().pushToast("剪映草稿匯出已開始，請將下載的 ZIP 解壓到剪映草稿目錄中", "success");
    } catch (err) {
      useAppStore.getState().pushToast(`剪映草稿匯出失敗：${(err as Error).message}`, "error");
    } finally {
      setJianyingExporting(false);
    }
  };

  const handleExportProject = async (scope: "current" | "full") => {
    if (!currentProjectName || exportingProject) return;

    setExportDialogOpen(false);
    setExportingProject(true);
    try {
      const { download_token, diagnostics } = await API.requestExportToken(currentProjectName, scope);
      const url = API.getExportDownloadUrl(currentProjectName, download_token, scope);
      triggerBrowserDownload(url);
      const diagnosticCount =
        diagnostics.blocking.length + diagnostics.auto_fixed.length + diagnostics.warnings.length;
      if (diagnosticCount > 0) {
        setExportDiagnostics(diagnostics);
        useAppStore.getState().pushToast(
          `專案 ZIP 已開始下載，匯出包包含 ${diagnosticCount} 筆診斷`,
          "warning",
        );
      } else {
        useAppStore.getState().pushToast("專案 ZIP 已開始下載", "success");
      }
    } catch (err) {
      useAppStore
        .getState()
        .pushToast(`匯出失敗：${(err as Error).message}`, "error");
    } finally {
      setExportingProject(false);
    }
  };

  return (
    <header className="workbench-panel-subtle flex h-16 shrink-0 items-center justify-between border-b px-4 backdrop-blur-xl">
      {/* ---- Left section ---- */}
      <div className="flex items-center gap-3">
        {/* Logo */}
        <img src="/android-chrome-192x192.png" alt="ArcReel" className="h-8 w-8 rounded-xl" />

        {/* Back to projects */}
        <button
          type="button"
          onClick={onNavigateBack}
          className="workbench-button-secondary flex items-center gap-1 rounded-xl px-2.5 py-1.5 text-sm"
          aria-label="返回專案大廳"
        >
          <ChevronLeft className="h-4 w-4" />
          <span className="hidden sm:inline">專案大廳</span>
        </button>

        {/* Divider */}
        <div className="h-5 w-px bg-[color:var(--wb-border-soft)]" />

        {/* Project name */}
        <div className="min-w-0">
          <div className="text-[11px] uppercase tracking-[0.2em] text-[color:var(--wb-text-dim)]">目前專案</div>
          <span className="block max-w-56 truncate text-sm font-medium text-[color:var(--wb-text-primary)]">
            {displayProjectTitle}
          </span>
        </div>

        {/* Content mode badge */}
        {contentMode && (
          <span className="rounded-full border border-white/6 bg-black/12 px-2.5 py-1 text-xs text-[color:var(--wb-text-muted)]">
            {modeBadgeText}
          </span>
        )}
      </div>

      {/* ---- Center section ---- */}
      <div className="hidden md:flex">
        <PhaseStepper currentPhase={currentPhase} onNavigate={handlePhaseNavigate} />
      </div>

      {/* ---- Right section ---- */}
      <div className="flex items-center gap-3">
        <div className="relative" ref={notificationAnchorRef}>
          <button
            type="button"
            onClick={() => setNotificationDrawerOpen(!notificationDrawerOpen)}
            className={`relative flex items-center gap-1 rounded-md px-2 py-1 text-xs transition-colors ${notificationDrawerOpen
                ? "workbench-status-warning"
                : "workbench-button-secondary"
              }`}
            title={`會話通知：${workspaceNotifications.length} 則`}
            aria-label="開啟通知中心"
          >
            <Bell className="h-3.5 w-3.5" />
            {unreadNotificationCount > 0 && (
              <span className="absolute -right-1.5 -top-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-amber-400 px-1 text-[10px] font-bold text-slate-950">
                {unreadNotificationCount > 9 ? "9+" : unreadNotificationCount}
              </span>
            )}
          </button>
          <WorkspaceNotificationsDrawer
            open={notificationDrawerOpen}
            onClose={() => setNotificationDrawerOpen(false)}
            anchorRef={notificationAnchorRef}
            onNavigate={handleNotificationNavigate}
          />
        </div>

        {/* Cost badge + UsageDrawer */}
        <div className="relative" ref={usageAnchorRef}>
          <button
            type="button"
            onClick={() => setUsageDrawerOpen(!usageDrawerOpen)}
            className={`flex items-center gap-1 rounded-md px-2 py-1 text-xs transition-colors ${usageDrawerOpen
                ? "workbench-panel-strong text-[color:var(--wb-accent)]"
                : "workbench-button-secondary"
              }`}
            title={`專案總花費：${costText}`}
          >
            <span className="font-mono">{costText}</span>
          </button>
          <UsageDrawer
            open={usageDrawerOpen}
            onClose={() => setUsageDrawerOpen(false)}
            projectName={currentProjectName}
            anchorRef={usageAnchorRef}
          />
        </div>

        {/* Task radar + TaskHud popover */}
        <div className="relative" ref={taskHudAnchorRef}>
          <button
            type="button"
            onClick={() => setTaskHudOpen(!taskHudOpen)}
            className={`relative rounded-md p-1.5 transition-colors ${taskHudOpen
                ? "workbench-panel-strong text-[color:var(--wb-accent)]"
                : "workbench-button-secondary"
              }`}
            title={`任務狀態：${stats.running} 執行中，${stats.queued} 排隊中`}
            aria-label="切換任務面板"
          >
            <Activity
              className={`h-4 w-4 ${runningCount > 0 ? "animate-pulse" : ""}`}
            />
            {/* Running task count badge */}
            {runningCount > 0 && (
              <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-indigo-500 px-1 text-[10px] font-bold text-white">
                {runningCount}
              </span>
            )}
          </button>
          <TaskHud anchorRef={taskHudAnchorRef} />
        </div>


        <div className="relative" ref={exportAnchorRef}>
          <button
            type="button"
            onClick={() => setExportDialogOpen(!exportDialogOpen)}
            disabled={!currentProjectName || exportingProject}
            className="workbench-button-secondary inline-flex items-center gap-1 rounded-xl px-2.5 py-1.5 text-xs disabled:cursor-not-allowed disabled:opacity-50"
            title="匯出目前專案 ZIP"
            aria-label="匯出目前專案 ZIP"
          >
            {exportingProject ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Download className="h-3.5 w-3.5" />
            )}
            <span className="hidden lg:inline">
              {exportingProject ? "匯出中..." : "匯出 ZIP"}
            </span>
          </button>
          <ExportScopeDialog
            open={exportDialogOpen}
            onClose={() => setExportDialogOpen(false)}
            onSelect={(scope) => { if (scope !== "jianying-draft") void handleExportProject(scope); }}
            anchorRef={exportAnchorRef}
            episodes={currentProjectData?.episodes ?? []}
            onJianyingExport={handleJianyingExport}
            jianyingExporting={jianyingExporting}
          />
        </div>

        {/* Settings (placeholder) */}
        <button
          type="button"
          onClick={() => setLocation(
            currentProjectName
              ? `~/app/projects/${encodeURIComponent(currentProjectName)}/settings`
              : "~/app/settings"
          )}
          className="workbench-button-secondary relative rounded-xl p-2"
          title="設定"
          aria-label="設定"
        >
          <Settings className="h-4 w-4" />
          {!isConfigComplete && !currentProjectName && (
            <span className="absolute right-0.5 top-0.5 h-2 w-2 rounded-full bg-rose-500" aria-label="設定不完整" />
          )}
        </button>

      </div>

      {exportDiagnostics !== null && (
        <ArchiveDiagnosticsDialog
          title="匯出診斷"
          description="匯出已完成預先檢查並產生 ZIP。以下問題是在匯出包中偵測到的。"
          sections={[
            { key: "blocking", title: "阻斷問題", tone: "border-red-400/25 bg-red-500/10 text-red-100", items: exportDiagnostics.blocking },
            { key: "auto_fixed", title: "已自動修復", tone: "border-indigo-400/25 bg-indigo-500/10 text-indigo-100", items: exportDiagnostics.auto_fixed },
            { key: "warnings", title: "警告", tone: "border-amber-400/25 bg-amber-500/10 text-amber-100", items: exportDiagnostics.warnings },
          ]}
          onClose={() => setExportDiagnostics(null)}
        />
      )}
    </header>
  );
}
