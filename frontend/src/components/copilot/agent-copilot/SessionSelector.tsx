import { useRef, useState } from "react";
import { ChevronDown, MessageSquare, Trash2 } from "lucide-react";
import { useAssistantStore } from "@/stores/assistant-store";
import { useConfirm } from "@/hooks/useConfirm";
import { Popover } from "@/components/ui/Popover";
import {
  ASSISTANT_PROVIDER_LABELS,
  resolveAssistantCapabilities,
} from "@/types";

function StatusDot({ status }: { status: string }) {
  const colorMap: Record<string, string> = {
    idle: "bg-gray-500",
    running: "bg-amber-400",
    completed: "bg-green-500",
    error: "bg-red-500",
    interrupted: "bg-gray-400",
  };
  return (
    <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${colorMap[status] ?? "bg-gray-500"}`} />
  );
}

function formatTime(isoStr: string | undefined): string {
  if (!isoStr) return "新會話";
  try {
    const d = new Date(isoStr);
    return `${(d.getMonth() + 1).toString().padStart(2, "0")}/${d.getDate().toString().padStart(2, "0")} ${d.getHours().toString().padStart(2, "0")}:${d.getMinutes().toString().padStart(2, "0")}`;
  } catch {
    return "新會話";
  }
}

export function SessionSelector({
  onSwitch,
  onDelete,
}: {
  onSwitch: (sessionId: string) => void;
  onDelete: (sessionId: string) => void;
}) {
  const { sessions, currentSessionId, isDraftSession } = useAssistantStore();
  const [open, setOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const confirm = useConfirm();

  const currentSession = sessions.find((s) => s.id === currentSessionId);
  const displayTitle = isDraftSession ? "新會話" : (currentSession?.title || formatTime(currentSession?.created_at));

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1 rounded px-1.5 py-0.5 text-xs text-gray-400 transition-colors hover:bg-gray-800 hover:text-gray-200"
        title="切換會話"
      >
        <MessageSquare className="h-3 w-3" />
        <span className="max-w-24 truncate">{displayTitle || "無會話"}</span>
        <ChevronDown className={`h-3 w-3 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {sessions.length > 0 && (
        <Popover
          open={open}
          onClose={() => setOpen(false)}
          anchorRef={dropdownRef}
          sideOffset={4}
          width="w-64"
          layer="assistantLocalPopover"
          className="rounded-lg border border-gray-700 shadow-xl"
        >
          <div className="max-h-60 overflow-y-auto py-1">
            {sessions.map((session) => {
              const isActive = session.id === currentSessionId;
              const title = session.title || formatTime(session.created_at);
              const sessionCapabilities = resolveAssistantCapabilities(session);
              const canResumeSession = sessionCapabilities.supports_resume;
              const providerLabel = ASSISTANT_PROVIDER_LABELS[sessionCapabilities.provider] ?? sessionCapabilities.provider;
              return (
                <div
                  key={session.id}
                  className={`group flex items-center gap-2 px-3 py-2 text-sm transition-colors ${
                    isActive
                      ? "bg-indigo-500/10 text-indigo-300"
                      : "text-gray-300 hover:bg-gray-800"
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => {
                      if (!canResumeSession && !isActive) return;
                      onSwitch(session.id);
                      setOpen(false);
                    }}
                    disabled={!canResumeSession && !isActive}
                    className="flex flex-1 items-center gap-2 truncate text-left disabled:cursor-not-allowed disabled:opacity-50"
                    title={!canResumeSession && !isActive ? `${providerLabel} 目前不支援恢復舊會話` : undefined}
                  >
                    <StatusDot status={session.status} />
                    <span className="min-w-0 flex-1 truncate">{title}</span>
                    <span className="shrink-0 rounded-full border border-gray-700 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-gray-500">
                      {sessionCapabilities.tier}
                    </span>
                  </button>
                  <button
                    type="button"
                    onClick={async (e) => {
                      e.stopPropagation();
                      const ok = await confirm({
                        message: "確定要刪除這個會話嗎？此操作無法復原。",
                        danger: true,
                      });
                      if (ok) onDelete(session.id);
                    }}
                    className="shrink-0 rounded p-0.5 text-gray-600 opacity-0 transition-opacity hover:text-red-400 group-hover:opacity-100"
                    title="刪除會話"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              );
            })}
          </div>
        </Popover>
      )}
    </div>
  );
}
