import { useState, useMemo, useRef } from "react";
import { Clock } from "lucide-react";
import { DEFAULT_DURATIONS } from "@/utils/provider-models";
import { useAppStore } from "@/stores/app-store";
import { Popover } from "@/components/ui/Popover";
import type { SegmentUpdateHandler } from "./types";

export function getDurationDisplayOptions(seconds: number, durationOptions: readonly number[]): number[] {
  const options =
    durationOptions.length === 1
      ? [...DEFAULT_DURATIONS, seconds]
      : [...durationOptions, seconds];
  return Array.from(new Set(options)).sort((a, b) => a - b);
}

export function getDurationOptionClassName(active: boolean, disabled: boolean): string {
  const base =
    "rounded px-3 py-1.5 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500";
  if (active) return `${base} bg-indigo-600 text-white`;
  if (disabled) return `${base} cursor-not-allowed text-gray-600`;
  return `${base} text-gray-300 hover:bg-gray-700`;
}

export function pushDurationAdjustmentToast(previous: number, next: number, reason?: string) {
  if (!reason) return;
  useAppStore
    .getState()
    .pushToast(`已自動將秒數從 ${previous} 調整為 ${next}（${reason}）`, "warning");
}

interface DurationSelectorProps {
  seconds: number;
  segmentId: string;
  onUpdatePrompt?: SegmentUpdateHandler;
  durationOptions?: number[];
  durationConstraintReason?: string;
}

/** Duration selector — clickable when onUpdatePrompt is provided, read-only otherwise. */
export function DurationSelector({
  seconds,
  segmentId,
  onUpdatePrompt,
  durationOptions = DEFAULT_DURATIONS as number[],
  durationConstraintReason,
}: DurationSelectorProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLButtonElement>(null);
  const displayOptions = useMemo(
    () => getDurationDisplayOptions(seconds, durationOptions),
    [durationOptions, seconds],
  );
  const allowedOptions = useMemo(() => new Set(durationOptions), [durationOptions]);

  if (!onUpdatePrompt) {
    return (
      <span className="inline-flex items-center gap-0.5 rounded bg-gray-700 px-1.5 py-0.5 text-xs text-gray-300">
        <Clock aria-hidden="true" className="h-3 w-3" />
        {seconds}s
      </span>
    );
  }

  return (
    <>
      <button
        ref={ref}
        onClick={() => setOpen((o) => !o)}
        className="inline-flex cursor-pointer items-center gap-0.5 rounded bg-gray-700 px-1.5 py-0.5 text-xs text-gray-300 hover:bg-gray-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
      >
        <Clock aria-hidden="true" className="h-3 w-3" />
        {seconds}s
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
        <div className="flex gap-1" role="radiogroup" aria-label="時長選擇">
          {displayOptions.map((d) => {
            const disabled = !allowedOptions.has(d);
            return (
              <button
                key={d}
                role="radio"
                aria-checked={d === seconds}
                disabled={disabled}
                title={disabled ? durationConstraintReason : undefined}
                onClick={() => {
                  if (disabled) return;
                  onUpdatePrompt(segmentId, "duration_seconds", d);
                  setOpen(false);
                }}
                className={getDurationOptionClassName(d === seconds, disabled)}
              >
                {d}s
              </button>
            );
          })}
        </div>
      </Popover>
    </>
  );
}
