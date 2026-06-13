import { useCallback, useEffect, useRef, useState, type RefObject } from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence } from "framer-motion";
import { Image, Video, Check, X, Loader2, ChevronDown } from "lucide-react";
import { useAnchoredPopover } from "@/hooks/useAnchoredPopover";
import { API, type TaskCancelPreviewResponse } from "@/api";
import { useAppStore } from "@/stores/app-store";
import { useTasksStore } from "@/stores/tasks-store";
import type { TaskItem } from "@/types";
import { UI_LAYERS } from "@/utils/ui-layers";
import { POPOVER_BG } from "@/components/ui/Popover";

type CancelConfirm =
  | {
      taskId: string;
      preview: TaskCancelPreviewResponse;
    }
  | {
      projectName: string;
      allCount: number;
    };

function isSingleCancelConfirm(
  confirm: CancelConfirm | null,
): confirm is Extract<CancelConfirm, { preview: TaskCancelPreviewResponse }> {
  return Boolean(confirm && "preview" in confirm);
}

function getCancelMessage(confirm: CancelConfirm | null): string {
  if (!confirm) return "";
  if (!isSingleCancelConfirm(confirm)) {
    return `確定取消所有 ${confirm.allCount} 個排隊任務？`;
  }

  const cascadeCount = confirm.preview.cascaded.length;
  return cascadeCount > 0 ? `取消此任務會同時取消 ${cascadeCount} 個依賴任務` : "確定取消此任務？";
}

function shouldAutoFade(status: TaskItem["status"]): boolean {
  return status === "succeeded" || status === "cancelled";
}

function isRecentTask(status: TaskItem["status"]): boolean {
  return status === "succeeded" || status === "failed" || status === "cancelled";
}

// ---------------------------------------------------------------------------
// Task status icon — visual indicator per task state
// ---------------------------------------------------------------------------

function TaskStatusIcon({ status }: { status: TaskItem["status"] }) {
  switch (status) {
    case "running":
      return <Loader2 className="h-3.5 w-3.5 animate-spin text-indigo-400" />;
    case "queued":
      return <div className="h-2 w-2 rounded-full bg-gray-500" />;
    case "succeeded":
      return <Check className="h-3.5 w-3.5 text-emerald-400" />;
    case "failed":
      return <X className="h-3.5 w-3.5 text-red-400" />;
    case "cancelled":
      return <X className="h-3.5 w-3.5 text-gray-500" />;
  }
}

// ---------------------------------------------------------------------------
// RunningProgressBar — 執行中任務的動態進度條
// ---------------------------------------------------------------------------

function RunningProgressBar() {
  return (
    <div className="relative mt-1 h-0.5 w-full overflow-hidden rounded-full bg-gray-800">
      <motion.div
        className="absolute inset-y-0 left-0 w-1/3 rounded-full bg-gradient-to-r from-indigo-500 via-indigo-400 to-indigo-500"
        animate={{ x: ["0%", "200%"] }}
        transition={{
          duration: 1.5,
          repeat: Infinity,
          ease: "easeInOut",
        }}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// TaskRow — 單個任務條目（含完成高亮、失敗展開、執行進度條）
// ---------------------------------------------------------------------------

function TaskRow({
  task,
  isFading,
  expandedErrorId,
  onToggleError,
  onCancel,
}: {
  task: TaskItem;
  isFading: boolean;
  expandedErrorId: string | null;
  onToggleError: (taskId: string) => void;
  onCancel?: (taskId: string) => void;
}) {
  const statusLabel: Record<TaskItem["status"], string> = {
    running: "生成中...",
    queued: "排隊中",
    succeeded: "已完成",
    failed: "失敗",
    cancelled: "已取消",
  };

  const statusColor: Record<TaskItem["status"], string> = {
    running: "text-indigo-400",
    queued: "text-gray-500",
    succeeded: "text-emerald-400",
    failed: "text-red-400",
    cancelled: "text-gray-400",
  };

  // 根據狀態確定行背景樣式
  const rowBg =
    task.status === "failed"
      ? "bg-red-500/10"
      : task.status === "succeeded" && !isFading
        ? "bg-emerald-500/10"
        : "";

  const isErrorExpanded = expandedErrorId === task.task_id;
  const errorDetail = readErrorDetail(task);
  const hasError = task.status === "failed" && Boolean(task.error_message || errorDetail);

  return (
    <motion.div
      layout
      initial={{ opacity: 0, height: 0 }}
      animate={{
        opacity: isFading ? 0 : 1,
        height: isFading ? 0 : "auto",
      }}
      exit={{ opacity: 0, height: 0 }}
      transition={{ duration: isFading ? 0.4 : 0.2 }}
      className="overflow-hidden"
    >
      {/* 主行內容 */}
      <div
        className={`flex items-center gap-2 px-3 py-1.5 text-sm ${rowBg} ${
          hasError ? "cursor-pointer hover:bg-red-500/15" : ""
        }`}
        onClick={hasError ? () => onToggleError(task.task_id) : undefined}
      >
        <TaskStatusIcon status={task.status} />
        <span className="font-mono text-xs text-gray-400">
          {task.resource_id}
        </span>
        <span className="flex-1 truncate text-gray-300">{task.task_type}</span>
        <span className={`text-xs ${statusColor[task.status]}`}>
          {statusLabel[task.status]}
        </span>
        {task.status === "cancelled" && task.cancelled_by === "cascade" && (
          <span className="text-xs text-gray-600">級聯</span>
        )}
        {task.status === "queued" && onCancel && (
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              onCancel(task.task_id);
            }}
            className="rounded p-0.5 text-gray-500 transition-colors hover:bg-gray-800 hover:text-red-300"
            aria-label={`取消任務 ${task.resource_id}`}
            title="取消任務"
          >
            <X className="h-3 w-3" />
          </button>
        )}
        {hasError && (
          <ChevronDown
            className={`h-3 w-3 text-gray-500 transition-transform ${
              isErrorExpanded ? "rotate-180" : ""
            }`}
          />
        )}
      </div>

      {/* 執行中任務的進度條 */}
      {task.status === "running" && (
        <div className="px-3 pb-1">
          <RunningProgressBar />
        </div>
      )}

      {/* 失敗任務的錯誤詳情展開區域 */}
      <AnimatePresence>
        {hasError && isErrorExpanded && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.15 }}
            className="overflow-hidden"
          >
            <div className="mx-3 mb-1.5 rounded bg-red-500/5 px-2 py-1.5 text-xs text-red-300/80">
              <TaskErrorDetail detail={errorDetail} fallback={task.error_message} />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// ChannelSection — 按圖片/影片通道分組，含自動淡出邏輯
// ---------------------------------------------------------------------------

function ChannelSection({
  title,
  icon: Icon,
  tasks,
  onCancel,
}: {
  title: string;
  icon: React.ComponentType<{ className?: string }>;
  tasks: TaskItem[];
  onCancel?: (taskId: string) => void;
}) {
  // 跟蹤正在淡出的任務 ID
  const [fadingIds, setFadingIds] = useState<Set<string>>(new Set());
  // 跟蹤已完全淡出（應隱藏）的任務 ID
  const [hiddenIds, setHiddenIds] = useState<Set<string>>(new Set());
  // 儲存定時器引用以便清理
  const timersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  // 失敗任務錯誤詳情展開狀態
  const [expandedErrorId, setExpandedErrorId] = useState<string | null>(null);

  const toggleError = useCallback((taskId: string) => {
    setExpandedErrorId((prev) => (prev === taskId ? null : taskId));
  }, []);

  // 監聽任務狀態變化，為終態任務設定自動淡出
  useEffect(() => {
    const autoFadeTasks = tasks.filter(
      (t) => shouldAutoFade(t.status) && !fadingIds.has(t.task_id) && !hiddenIds.has(t.task_id),
    );

    for (const task of autoFadeTasks) {
      if (timersRef.current.has(task.task_id)) continue;

      // 3 秒後開始淡出動畫
      const fadeTimer = setTimeout(() => {
        setFadingIds((prev) => new Set(prev).add(task.task_id));

        // 淡出動畫完成後（400ms）標記為隱藏
        const hideTimer = setTimeout(() => {
          setHiddenIds((prev) => new Set(prev).add(task.task_id));
          timersRef.current.delete(task.task_id);
        }, 400);

        timersRef.current.set(task.task_id + "_hide", hideTimer);
      }, 3000);

      timersRef.current.set(task.task_id, fadeTimer);
    }

    return () => {
      // 元件解除安裝時清理所有定時器
      for (const timer of timersRef.current.values()) {
        clearTimeout(timer);
      }
    };
  }, [tasks, fadingIds, hiddenIds]);

  const running = tasks.filter((t) => t.status === "running");
  const queued = tasks.filter((t) => t.status === "queued");
  const recent = tasks
    .filter((t) => isRecentTask(t.status))
    .filter((t) => !hiddenIds.has(t.task_id))
    .slice(0, 5);

  const visible = [...running, ...queued, ...recent];

  return (
    <div>
      <div className="flex items-center gap-2 px-3 py-2 text-xs font-semibold text-gray-400">
        <Icon className="h-3.5 w-3.5" />
        {title}
        {running.length > 0 && (
          <span className="ml-auto text-indigo-400">
            {running.length} 執行中
          </span>
        )}
      </div>
      <AnimatePresence>
        {visible.map((task) => (
          <TaskRow
            key={task.task_id}
            task={task}
            isFading={fadingIds.has(task.task_id)}
            expandedErrorId={expandedErrorId}
            onToggleError={toggleError}
            onCancel={onCancel}
          />
        ))}
      </AnimatePresence>
      {visible.length === 0 && (
        <div className="px-3 py-2 text-xs text-gray-600">暫無任務</div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// TaskHud — 彈出面板，實時展示任務佇列狀態
// ---------------------------------------------------------------------------

export function TaskHud({ anchorRef }: { anchorRef: RefObject<HTMLElement | null> }) {
  const { taskHudOpen, setTaskHudOpen } = useAppStore();
  const { tasks, stats, setTasks, upsertTask, setStats } = useTasksStore();
  const [cancelConfirm, setCancelConfirm] = useState<CancelConfirm | null>(null);
  const { panelRef, positionStyle } = useAnchoredPopover({
    open: taskHudOpen,
    anchorRef,
    onClose: () => setTaskHudOpen(false),
    sideOffset: 4,
  });

  const imageTasks = tasks.filter((t) => t.media_type === "image");
  const videoTasks = tasks.filter((t) => t.media_type === "video");
  const cancelCascaded = isSingleCancelConfirm(cancelConfirm) ? cancelConfirm.preview.cascaded : [];
  const cancelMessage = getCancelMessage(cancelConfirm);

  const applyCancelledStats = useCallback(
    (count: number) => {
      if (count <= 0) return;
      setStats({
        ...stats,
        queued: Math.max(0, stats.queued - count),
        cancelled: stats.cancelled + count,
      });
    },
    [setStats, stats],
  );

  const handleCancelSingle = useCallback(async (taskId: string) => {
    try {
      const preview = await API.cancelPreview(taskId);
      setCancelConfirm({ taskId, preview });
    } catch {
      setCancelConfirm(null);
    }
  }, []);

  const handleCancelAll = useCallback(async () => {
    const queuedTask = tasks.find((task) => task.status === "queued");
    if (!queuedTask) return;

    try {
      const preview = await API.cancelAllPreview(queuedTask.project_name);
      if (preview.queued_count <= 0) return;
      setCancelConfirm({ projectName: queuedTask.project_name, allCount: preview.queued_count });
    } catch {
      setCancelConfirm(null);
    }
  }, [tasks]);

  const confirmCancel = useCallback(async () => {
    if (!cancelConfirm) return;

    try {
      if (isSingleCancelConfirm(cancelConfirm)) {
        const result = await API.cancelTask(cancelConfirm.taskId);
        for (const task of result.cancelled) {
          upsertTask(task);
        }
        applyCancelledStats(result.cancelled.length);
      } else {
        const result = await API.cancelAllQueued(cancelConfirm.projectName);
        const now = new Date().toISOString();
        const updatedTasks = tasks.map((task) =>
          task.project_name === cancelConfirm.projectName && task.status === "queued"
            ? {
                ...task,
                status: "cancelled" as const,
                cancelled_by: "user" as const,
                finished_at: now,
                updated_at: now,
              }
            : task,
        );
        setTasks(updatedTasks);
        applyCancelledStats(result.cancelled_count);
      }
    } finally {
      setCancelConfirm(null);
    }
  }, [applyCancelledStats, cancelConfirm, setTasks, tasks, upsertTask]);

  if (typeof document === "undefined") return null;

  return createPortal(
    <AnimatePresence>
      {taskHudOpen && (
        <motion.div
          ref={panelRef}
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.15 }}
          className={`fixed w-80 isolate rounded-lg border border-gray-800 shadow-xl ${UI_LAYERS.workspacePopover}`}
          style={{
            ...positionStyle,
            backgroundColor: POPOVER_BG,
          }}
        >
          {/* 統計欄 */}
          <div className="flex gap-3 border-b border-gray-800 px-3 py-2 text-xs text-gray-400">
            <span>
              排隊{" "}
              <strong className="text-gray-200">{stats.queued}</strong>
            </span>
            <span>
              執行{" "}
              <strong className="text-indigo-400">{stats.running}</strong>
            </span>
            <span>
              完成{" "}
              <strong className="text-emerald-400">{stats.succeeded}</strong>
            </span>
            <span>
              失敗{" "}
              <strong className="text-red-400">{stats.failed}</strong>
            </span>
            {stats.cancelled > 0 && (
              <span>
                取消{" "}
                <strong className="text-gray-400">{stats.cancelled}</strong>
              </span>
            )}
            {stats.queued > 0 && (
              <button
                type="button"
                onClick={handleCancelAll}
                className="ml-auto flex items-center gap-1 rounded px-1 py-0.5 text-gray-500 transition-colors hover:bg-gray-800 hover:text-red-300"
                aria-label="取消所有排隊任務"
                title="取消所有排隊任務"
              >
                <X className="h-3 w-3" />
                <span>全部取消</span>
              </button>
            )}
          </div>

          {/* 雙通道 */}
          <div className="max-h-80 divide-y divide-gray-800/50 overflow-y-auto">
            <ChannelSection title="圖片通道" icon={Image} tasks={imageTasks} onCancel={handleCancelSingle} />
            <ChannelSection title="影片通道" icon={Video} tasks={videoTasks} onCancel={handleCancelSingle} />
          </div>
          {cancelConfirm && (
            <div className="border-t border-gray-800 px-3 py-2">
              <p className="text-xs text-gray-300">{cancelMessage}</p>
              {cancelCascaded.length > 0 && (
                <ul className="mt-1 max-h-20 overflow-y-auto text-xs text-gray-500">
                  {cancelCascaded.map((task) => (
                    <li key={task.task_id}>
                      {task.task_type} / {task.resource_id}
                    </li>
                  ))}
                </ul>
              )}
              <div className="mt-2 flex gap-2">
                <button
                  type="button"
                  onClick={confirmCancel}
                  className="rounded bg-red-600/80 px-2 py-0.5 text-xs text-white transition-colors hover:bg-red-600"
                >
                  確認取消
                </button>
                <button
                  type="button"
                  onClick={() => setCancelConfirm(null)}
                  className="rounded px-2 py-0.5 text-xs text-gray-400 transition-colors hover:bg-gray-800"
                >
                  返回
                </button>
              </div>
            </div>
          )}
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
}

interface TaskErrorDetailData {
  code?: string;
  message?: string;
  model?: string;
  hint?: string;
}

function readErrorDetail(task: TaskItem): TaskErrorDetailData | null {
  const result = task.result;
  if (!result || typeof result !== "object") return null;
  const detail = (result as Record<string, unknown>).error_detail;
  if (!detail || typeof detail !== "object") return null;
  return detail as TaskErrorDetailData;
}

function TaskErrorDetail({
  detail,
  fallback,
}: {
  detail: TaskErrorDetailData | null;
  fallback?: string | null;
}) {
  if (detail?.code === "veo_invalid_combination") {
    return (
      <div className="flex flex-col gap-1">
        <div>{detail.message ?? fallback}</div>
        {detail.hint && <div className="text-red-300/60">{detail.hint}</div>}
        {detail.model && (
          <div className="font-mono text-[10px] text-red-300/40">
            model: {detail.model}
          </div>
        )}
      </div>
    );
  }
  return <>{fallback}</>;
}
