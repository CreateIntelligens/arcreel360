import { useState, useEffect, useCallback, useMemo } from "react";
import { API } from "@/api";
import type { UsageStat } from "@/types";

const currencyFmt = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const percentFmt = new Intl.NumberFormat("zh-CN", { style: "percent", maximumFractionDigits: 0 });

const TIME_RANGES = [
  { label: "最近 7 天", days: 7 },
  { label: "最近 30 天", days: 30 },
  { label: "全部", days: 0 },
];

export function UsageStatsSection() {
  const [stats, setStats] = useState<UsageStat[]>([]);
  const [loading, setLoading] = useState(true);
  const [timeRange, setTimeRange] = useState(7);
  const [providerFilter, setProviderFilter] = useState<string>("");

  const fetchStats = useCallback(async () => {
    setLoading(true);
    const params: { provider?: string; start?: string; end?: string } = {};
    if (providerFilter) params.provider = providerFilter;
    if (timeRange > 0) {
      const start = new Date();
      start.setDate(start.getDate() - timeRange);
      params.start = start.toISOString().split("T")[0];
      params.end = new Date().toISOString().split("T")[0];
    }
    try {
      const res = await API.getUsageStatsGrouped(params);
      setStats(res.stats || []);
    } catch {
      setStats([]);
    }
    setLoading(false);
  }, [timeRange, providerFilter]);

  useEffect(() => {
    void fetchStats();
  }, [fetchStats]);

  // Derive unique providers for filter dropdown
  const providers = useMemo(
    () => Array.from(new Set(stats.map((s) => s.provider))).sort(),
    [stats],
  );

  return (
    <div className="space-y-6 p-6">
      <div>
        <div className="workbench-kicker text-[11px] font-semibold">Provider Cost Signals</div>
        <h3 className="mt-1 text-lg font-semibold text-[color:var(--wb-text-primary)]">用量統計</h3>
        <p className="mt-1 text-sm text-[color:var(--wb-text-muted)]">檢視各供應商的 API 呼叫統計</p>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        {TIME_RANGES.map((r) => (
          <button
            key={r.days}
            type="button"
            onClick={() => setTimeRange(r.days)}
            className={`rounded-xl px-3.5 py-2 text-sm focus-visible:outline-none ${
              timeRange === r.days
                ? "workbench-button-primary"
                : "workbench-button-secondary"
            }`}
          >
            {r.label}
          </button>
        ))}
        {providers.length > 0 && (
          <select
            value={providerFilter}
            onChange={(e) => setProviderFilter(e.target.value)}
            aria-label="依供應商篩選"
            className="workbench-input rounded-xl px-3 py-2 text-sm focus:outline-none"
          >
            <option value="">全部供應商</option>
            {providers.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        )}
      </div>

      {/* Stats */}
      {loading ? (
        <div className="text-sm text-[color:var(--wb-text-muted)]">載入中…</div>
      ) : stats.length === 0 ? (
        <div className="workbench-panel-subtle rounded-2xl px-4 py-4 text-sm text-[color:var(--wb-text-muted)]">暫無資料</div>
      ) : (
        <div className="space-y-3">
          {stats.map((s) => (
            <div key={`${s.provider}-${s.call_type}`} className="workbench-panel rounded-2xl p-4">
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-sm font-medium text-[color:var(--wb-text-primary)]">{s.display_name ?? s.provider}</span>
                  <span className="ml-2 text-xs text-[color:var(--wb-text-muted)]">{s.call_type}</span>
                </div>
                <span className="text-sm text-[color:var(--wb-text-secondary)]">
                  {currencyFmt.format(s.total_cost_usd)}
                </span>
              </div>
              <div className="mt-3 flex flex-wrap gap-3 text-xs tabular-nums text-[color:var(--wb-text-muted)]">
                <span className="rounded-full border border-white/6 bg-black/12 px-2.5 py-1">呼叫：{s.total_calls}</span>
                <span className="rounded-full border border-white/6 bg-black/12 px-2.5 py-1">成功：{s.success_calls}</span>
                <span>
                  成功率：{" "}
                  {s.total_calls > 0
                    ? percentFmt.format(s.success_calls / s.total_calls)
                    : "0%"}
                </span>
                {s.call_type === "text" ? (
                  s.total_calls > 0 && <span>型別：文字生成</span>
                ) : s.total_duration_seconds !== undefined && (
                  <span>時長：{s.total_duration_seconds}s</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
