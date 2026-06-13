import { useEffect, useRef } from "react";
import { API } from "@/api";
import { useTasksStore } from "@/stores/tasks-store";

const POLL_INTERVAL_MS = 3000;

/**
 * 輪詢任務佇列狀態的 Hook。
 * 掛載時立即拉取一次，之後每 3 秒輪詢，解除安裝時清理。
 *
 * 替代原先的 EventSource SSE 長連線，釋放瀏覽器連線槽位
 * （Chrome HTTP/1.1 同域名 6 連線限制）。
 */
export function useTasksSSE(projectName?: string | null): void {
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const { setTasks, setStats, setConnected } = useTasksStore();

  useEffect(() => {
    let disposed = false;

    async function poll() {
      try {
        const [tasksRes, statsRes] = await Promise.all([
          API.listTasks({
            projectName: projectName ?? undefined,
            pageSize: 200,
          }),
          API.getTaskStats(projectName ?? null),
        ]);
        if (disposed) return;
        setTasks(tasksRes.items);
        // REST returns { stats: {...} }
        const stats = (statsRes as any).stats ?? statsRes;
        setStats(stats);
        setConnected(true);
      } catch {
        if (disposed) return;
        setConnected(false);
      }
    }

    // Initial fetch
    poll();

    // Periodic polling
    timerRef.current = setInterval(() => {
      if (!disposed) poll();
    }, POLL_INTERVAL_MS);

    return () => {
      disposed = true;
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
      setConnected(false);
    };
  }, [projectName, setTasks, setStats, setConnected]);
}
