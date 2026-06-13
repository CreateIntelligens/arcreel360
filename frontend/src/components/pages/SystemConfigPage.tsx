import { useEffect, useMemo } from "react";
import { Link, useLocation, useSearch } from "wouter";
import { AlertTriangle, BarChart3, Bot, ChevronLeft, Film, KeyRound, Plug } from "lucide-react";
import { useConfigStatusStore } from "@/stores/config-status-store";
import { AgentConfigTab } from "./AgentConfigTab";
import { ApiKeysTab } from "./ApiKeysTab";
import { MediaModelSection } from "./settings/MediaModelSection";
import { ProviderSection } from "./ProviderSection";
import { UsageStatsSection } from "./settings/UsageStatsSection";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type SettingsSection = "agent" | "providers" | "media" | "usage" | "api-keys";

// ---------------------------------------------------------------------------
// Sidebar navigation config
// ---------------------------------------------------------------------------

const SECTION_LIST: { id: SettingsSection; label: string; Icon: React.ComponentType<{ className?: string }> }[] = [
  { id: "agent", label: "AI Agent", Icon: Bot },
  { id: "providers", label: "供應商", Icon: Plug },
  { id: "media", label: "模型選擇", Icon: Film },
  { id: "usage", label: "用量統計", Icon: BarChart3 },
  { id: "api-keys", label: "API 管理", Icon: KeyRound },
];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function SystemConfigPage() {
  const [location, navigate] = useLocation();
  const search = useSearch();

  const activeSection = useMemo((): SettingsSection => {
    const section = new URLSearchParams(search).get("section");
    if (section === "providers") return "providers";
    if (section === "media") return "media";
    if (section === "usage") return "usage";
    if (section === "api-keys") return "api-keys";
    return "agent";
  }, [search]);

  const setActiveSection = (section: SettingsSection) => {
    const params = new URLSearchParams(search);
    params.set("section", section);
    navigate(`${location}?${params.toString()}`, { replace: true });
  };

  const configIssues = useConfigStatusStore((s) => s.issues);
  const fetchConfigStatus = useConfigStatusStore((s) => s.fetch);

  useEffect(() => {
    void fetchConfigStatus();
  }, [fetchConfigStatus]);

  // -------------------------------------------------------------------------
  // Main render
  // -------------------------------------------------------------------------

  return (
    <div className="workbench-shell flex h-screen flex-col text-[color:var(--wb-text-primary)]">
      {/* Page header */}
      <header className="shrink-0 border-b border-[color:var(--wb-border-soft)] px-6 py-5 backdrop-blur-xl">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <Link
              href="/app/projects"
              className="workbench-button-secondary inline-flex items-center gap-2 rounded-xl px-3 py-2 text-sm focus-visible:outline-none"
              aria-label="返回專案大廳"
            >
              <ChevronLeft className="h-4 w-4" />
              返回
            </Link>
            <div>
              <div className="workbench-kicker text-[11px] font-semibold">工作臺設定中心</div>
              <h1 className="mt-1 text-xl font-semibold text-[color:var(--wb-text-primary)]">設定</h1>
              <p className="text-sm text-[color:var(--wb-text-muted)]">系統設定與 API 存取管理</p>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <div className="rounded-2xl border border-white/6 bg-black/12 px-4 py-3">
              <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--wb-text-dim)]">分割槽</div>
              <div className="mt-1 text-sm font-medium text-[color:var(--wb-text-secondary)]">{SECTION_LIST.length} 個</div>
            </div>
            <div className="rounded-2xl border border-white/6 bg-black/12 px-4 py-3">
              <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--wb-text-dim)]">缺失項</div>
              <div className="mt-1 text-sm font-medium text-[color:var(--wb-text-secondary)]">{configIssues.length} 項</div>
            </div>
            <div className="rounded-2xl border border-white/6 bg-black/12 px-4 py-3">
              <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--wb-text-dim)]">目前分割槽</div>
              <div className="mt-1 text-sm font-medium text-[color:var(--wb-text-secondary)]">{SECTION_LIST.find((section) => section.id === activeSection)?.label ?? "AI Agent"}</div>
            </div>
          </div>
        </div>
      </header>

      {/* Body: sidebar + content */}
      <div className="flex min-h-0 flex-1 gap-6 px-6 py-6">
        {/* Sidebar */}
        <nav className="workbench-panel-subtle w-58 shrink-0 rounded-[1.4rem] p-3">
          {SECTION_LIST.map(({ id, label, Icon }) => {
            const isActive = activeSection === id;
            return (
              <button
                key={id}
                type="button"
                onClick={() => setActiveSection(id)}
                className={`flex w-full items-center gap-3 rounded-xl px-4 py-3 text-sm transition-colors focus-visible:outline-none ${
                  isActive
                    ? "workbench-panel-strong text-[color:var(--wb-text-primary)]"
                    : "text-[color:var(--wb-text-muted)] hover:bg-black/12 hover:text-[color:var(--wb-text-primary)]"
                }`}
              >
                <Icon className="h-4 w-4" />
                {label}
              </button>
            );
          })}
        </nav>

        {/* Content area */}
        <div className="workbench-panel flex-1 overflow-y-auto rounded-[1.4rem]">
          {/* Config warning banner */}
          {configIssues.length > 0 && (
            <div className="border-b border-[color:var(--wb-border-soft)] px-6 py-4">
              <div className="workbench-status-warning flex items-start gap-3 rounded-2xl px-4 py-3">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-[color:var(--wb-warning)]" />
                <div className="text-sm">
                  <span className="font-medium">以下必填設定尚未完成：</span>
                  <ul className="mt-1 space-y-0.5">
                    {configIssues.map((issue) => (
                      <li key={issue.key}>
                        <button
                          type="button"
                          onClick={() => setActiveSection(issue.tab)}
                          className="rounded underline underline-offset-2 hover:text-white focus-visible:outline-none"
                        >
                          {issue.label}
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          )}

          {/* Section content */}
          {activeSection === "agent" && <AgentConfigTab visible={true} />}
          {activeSection === "providers" && <ProviderSection />}
          {activeSection === "media" && <MediaModelSection />}
          {activeSection === "usage" && <UsageStatsSection />}
          {activeSection === "api-keys" && (
            <div className="p-6">
              <ApiKeysTab />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
