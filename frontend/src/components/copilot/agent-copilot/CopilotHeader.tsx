import { Bot, PanelRightClose, Plus } from "lucide-react";
import { SessionSelector } from "./SessionSelector";

interface CopilotHeaderProps {
  providerLabel: string;
  isRunning: boolean;
  onTogglePanel: () => void;
  onCreateNewSession: () => void;
  onSwitchSession: (sessionId: string) => void;
  onDeleteSession: (sessionId: string) => void;
}

export function CopilotHeader({
  providerLabel,
  isRunning,
  onTogglePanel,
  onCreateNewSession,
  onSwitchSession,
  onDeleteSession,
}: CopilotHeaderProps) {
  return (
    <div className="flex h-10 items-center justify-between border-b border-gray-800 px-3">
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onTogglePanel}
          className="rounded p-1 text-gray-400 transition-colors hover:bg-gray-800 hover:text-gray-200"
          title="收起助理面板"
        >
          <PanelRightClose className="h-4 w-4" />
        </button>
        <Bot className="h-4 w-4 text-indigo-400" />
        <span className="text-sm font-medium text-gray-300">ArcReel AI Agent</span>
        <span className="rounded-full border border-gray-700 px-2 py-0.5 text-[10px] uppercase tracking-wide text-gray-500">
          {providerLabel}
        </span>
      </div>
      <div className="flex items-center gap-1">
        {isRunning && (
          <span className="flex items-center gap-1.5 text-xs text-indigo-400 mr-1">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-indigo-400" />
            思考中
          </span>
        )}
        <SessionSelector onSwitch={onSwitchSession} onDelete={onDeleteSession} />
        <button
          type="button"
          onClick={onCreateNewSession}
          className="rounded p-1 text-gray-400 transition-colors hover:bg-gray-800 hover:text-gray-200"
          title="新建會話"
        >
          <Plus className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
