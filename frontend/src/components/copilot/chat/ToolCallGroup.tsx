import { useState } from "react";
import { ChevronRight } from "lucide-react";
import type { ContentBlock } from "@/types";
import { cn } from "./utils";
import { ToolCallWithResult } from "./ToolCallWithResult";

interface ToolCallGroupProps {
  blocks: ContentBlock[];
}

/**
 * 將連續多次 tool_use 收合為一個可展開的組塊，避免冗長的工具呼叫洗版。
 * 預設摺疊；展開後顯示組內每個 tool_use 的完整 ToolCallWithResult。
 */
export function ToolCallGroup({ blocks }: ToolCallGroupProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  const total = blocks.length;
  const completed = blocks.filter((b) => b.result !== undefined).length;
  const hasError = blocks.some((b) => b.is_error);
  const allDone = completed === total;

  const statusIcon = hasError ? "✗" : allDone ? "✓" : "…";
  const statusColor = hasError
    ? "text-red-400"
    : allDone
      ? "text-emerald-400"
      : "text-slate-500";

  const toolNames = blocks
    .map((b) => b.name)
    .filter((n): n is string => typeof n === "string" && n.length > 0);
  const uniqueNames = Array.from(new Set(toolNames));
  const summary =
    uniqueNames.length === 1
      ? `${uniqueNames[0]} × ${total}`
      : `${total} 次呼叫：${uniqueNames.slice(0, 3).join("、")}${uniqueNames.length > 3 ? "…" : ""}`;

  return (
    <div className="my-1.5 rounded-lg border border-white/15 bg-ink-800/40 overflow-hidden min-w-0">
      <button
        type="button"
        onClick={() => setIsExpanded((v) => !v)}
        className="w-full px-2.5 py-1.5 flex items-center justify-between text-left hover:bg-white/5 transition-colors"
      >
        <div className="flex items-center gap-1.5 min-w-0 flex-1 overflow-hidden">
          <span className="text-[10px] font-semibold uppercase shrink-0 text-amber-400">
            工具呼叫
          </span>
          <span className="text-[11px] text-slate-300 truncate">{summary}</span>
        </div>
        <div className="flex items-center gap-1.5 shrink-0 ml-1.5">
          <span className={cn("text-[10px] tabular-nums", statusColor)}>
            {completed}/{total}
          </span>
          <span className={cn("text-xs font-medium", statusColor)}>{statusIcon}</span>
          <ChevronRight
            className={cn(
              "h-3 w-3 text-slate-500 transition-transform",
              isExpanded && "rotate-90",
            )}
          />
        </div>
      </button>

      {isExpanded && (
        <div className="border-t border-white/10 px-2 py-1.5">
          {blocks.map((block, index) => (
            <ToolCallWithResult key={block.id ?? `group-${index}`} block={block} />
          ))}
        </div>
      )}
    </div>
  );
}
