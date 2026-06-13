import { useLocation } from "wouter";
import { Bot } from "lucide-react";
import { GlobalHeader } from "./GlobalHeader";
import { AssetSidebar } from "./AssetSidebar";
import { AgentCopilot } from "@/components/copilot/AgentCopilot";
import { useTasksSSE } from "@/hooks/useTasksSSE";
import { useProjectEventsSSE } from "@/hooks/useProjectEventsSSE";
import { useProjectsStore } from "@/stores/projects-store";
import { useAppStore } from "@/stores/app-store";
import { UI_LAYERS } from "@/utils/ui-layers";

// ---------------------------------------------------------------------------
// StudioLayout — three-column studio workspace shell
// ---------------------------------------------------------------------------

interface StudioLayoutProps {
  children: React.ReactNode;
}

export function StudioLayout({ children }: StudioLayoutProps) {
  const [, setLocation] = useLocation();
  const currentProjectName = useProjectsStore((s) => s.currentProjectName);
  const assistantPanelOpen = useAppStore((s) => s.assistantPanelOpen);
  const toggleAssistantPanel = useAppStore((s) => s.toggleAssistantPanel);

  // 進入工作區時連線任務 SSE 流
  useTasksSSE(currentProjectName);
  useProjectEventsSSE(currentProjectName);

  return (
    <div className="workbench-shell workbench-grid flex h-screen flex-col text-[color:var(--wb-text-primary)]">
      <GlobalHeader onNavigateBack={() => setLocation("~/app/projects")} />
      <div className="flex flex-1 overflow-hidden">
        <AssetSidebar className="w-[15%] min-w-50 border-r border-[color:var(--wb-border-soft)]" />
        <main className="flex-1 overflow-auto border-l border-r border-white/4 bg-[rgba(8,13,23,0.54)]">
          {children}
        </main>
        <div
          className={`workbench-panel-subtle shrink-0 overflow-hidden transition-[width,min-width,border-color] duration-300 ease-in-out ${
            assistantPanelOpen ? "border-l border-[color:var(--wb-border-soft)]" : "border-l border-transparent"
          }`}
          style={{
            width: assistantPanelOpen ? "40%" : "0",
            minWidth: assistantPanelOpen ? "22.5rem" : "0",
          }}
        >
          {/* 始終渲染但在收起時隱藏，保持狀態 */}
          <div
            className={`h-full transition-opacity duration-200 ${
              assistantPanelOpen ? "opacity-100" : "opacity-0 pointer-events-none"
            }`}
          >
            <AgentCopilot />
          </div>
        </div>
      </div>

      {/* 懸浮助手球 — 收起時固定在右上角 */}
      <button
        type="button"
        onClick={toggleAssistantPanel}
        className={`workbench-button-primary fixed right-4 top-18 flex h-11 w-11 items-center justify-center rounded-2xl transition-all duration-300 ease-in-out ${UI_LAYERS.workspaceFloating} ${
          assistantPanelOpen
            ? "pointer-events-none scale-0 opacity-0"
            : "cursor-pointer scale-100 opacity-100"
        }`}
        style={{ transitionDelay: assistantPanelOpen ? "0ms" : "200ms" }}
        title="展開助手面板"
        aria-label="展開助手面板"
      >
        <Bot className="h-5 w-5 text-white" />
      </button>
    </div>
  );
}
