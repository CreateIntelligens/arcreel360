import { useState, useMemo, useRef } from "react";
import { Popover } from "@/components/ui/Popover";
import type { TransitionType } from "@/types";

export const TRANSITION_LABELS: Record<TransitionType, string> = {
  cut: "Cut",
  fade: "Fade",
  dissolve: "Dissolve",
};

export function getPillOptionClassName(active: boolean): string {
  const base =
    "rounded px-3 py-1.5 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500";
  return active ? `${base} bg-indigo-600 text-white` : `${base} text-gray-300 hover:bg-gray-700`;
}

interface OptionPillSelectorProps {
  value: string;
  options: readonly string[];
  icon: React.ReactNode;
  ariaLabel: string;
  onSelect?: (next: string) => void;
}

/**
 * Generic string-option pill selector (used for video resolution & image size).
 * Read-only chip when onSelect is absent or only one option is available.
 */
export function OptionPillSelector({
  value,
  options,
  icon,
  ariaLabel,
  onSelect,
}: OptionPillSelectorProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLButtonElement>(null);
  // Always include the current value so an out-of-range override is still shown.
  const displayOptions = useMemo(
    () => Array.from(new Set([...options, value])).filter(Boolean),
    [options, value],
  );
  const interactive = Boolean(onSelect) && displayOptions.length > 1;

  if (!interactive) {
    return (
      <span className="inline-flex items-center gap-0.5 rounded bg-gray-700 px-1.5 py-0.5 text-xs text-gray-300">
        {icon}
        {value}
      </span>
    );
  }

  return (
    <>
      <button
        ref={ref}
        onClick={() => setOpen((o) => !o)}
        aria-label={ariaLabel}
        className="inline-flex cursor-pointer items-center gap-0.5 rounded bg-gray-700 px-1.5 py-0.5 text-xs text-gray-300 hover:bg-gray-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
      >
        {icon}
        {value}
      </button>
      <Popover
        open={open}
        onClose={() => setOpen(false)}
        anchorRef={ref}
        width="w-auto"
        className="rounded-lg border border-gray-700 p-1.5 shadow-xl"
        align="start"
        sideOffset={6}
      >
        <div className="flex gap-1" role="radiogroup" aria-label={ariaLabel}>
          {displayOptions.map((opt) => (
            <button
              key={opt}
              role="radio"
              aria-checked={opt === value}
              onClick={() => {
                onSelect?.(opt);
                setOpen(false);
              }}
              className={getPillOptionClassName(opt === value)}
            >
              {opt}
            </button>
          ))}
        </div>
      </Popover>
    </>
  );
}

/** Segment break separator rendered above a card when segment_break is true. */
export function SegmentBreakSeparator() {
  return (
    <div className="flex items-center gap-3 py-2">
      <div className="flex-1 border-t-2 border-dashed border-amber-600/40" />
      <span className="text-[10px] font-semibold uppercase tracking-wider text-amber-500/70">
        Segment Break
      </span>
      <div className="flex-1 border-t-2 border-dashed border-amber-600/40" />
    </div>
  );
}

/** Transition indicator between cards. */
export function TransitionIndicator({ type }: { type: TransitionType }) {
  return (
    <div className="flex items-center justify-center py-1.5">
      <span className="rounded bg-gray-800 px-2 py-0.5 text-[10px] font-medium text-gray-500">
        {TRANSITION_LABELS[type] ?? type}
      </span>
    </div>
  );
}
