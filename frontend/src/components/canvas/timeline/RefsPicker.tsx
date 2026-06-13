import { useEffect, useRef, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import type { PreprocessRefs } from "@/api";

/**
 * 拆段時可帶入的 project context 設定。
 *
 * UI：
 *   - 「世界觀」「風格」：單一勾選。
 *   - 「角色」「道具」「場景」：父勾選 + 可展開的子項清單，
 *     父層三態（全勾 / 全不勾 / 部分勾 indeterminate）。
 *
 * value 結構與 `PreprocessRefs` 完全一致（子層 `null` = 全帶）。
 */
export type RefsValue = PreprocessRefs;

export type RefsCatalog = {
  /** 是否已生成世界觀（false 時「世界觀」勾選會 disable）。 */
  hasOverview: boolean;
  /** 全部角色名稱（順序保留 `Object.keys` 順序）。 */
  characters: string[];
  /** 全部道具名稱。 */
  clues: string[];
  /** 全部場景名稱。 */
  scenes: string[];
};

type Group = "characters" | "clues" | "scenes";

const GROUP_LABEL: Record<Group, string> = {
  characters: "角色",
  clues: "道具",
  scenes: "場景",
};

const GROUPS: Group[] = ["characters", "clues", "scenes"];
const CHECKBOX_CLASS =
  "h-3.5 w-3.5 rounded border-gray-700 bg-gray-900 text-indigo-600 focus:ring-0 focus:ring-offset-0";

export function defaultRefsValue(catalog: RefsCatalog): RefsValue {
  return {
    overview: catalog.hasOverview,
    style: true,
    characters: null,
    clues: null,
    scenes: null,
  };
}

export function hasCustomRefs(value: RefsValue, catalog: RefsCatalog): boolean {
  const defaults = defaultRefsValue(catalog);
  return (
    value.overview !== defaults.overview ||
    value.style !== defaults.style ||
    value.characters !== null ||
    value.clues !== null ||
    value.scenes !== null
  );
}

export function normalizeGroup(
  selected: Set<string>,
  all: string[],
): string[] | null {
  if (all.length === 0) return null;
  if (selected.size === all.length) return null;
  return all.filter((name) => selected.has(name));
}

type TriState = "checked" | "unchecked" | "indeterminate";

function computeTriState(selected: Set<string>, all: string[]): TriState {
  if (all.length === 0 || selected.size === 0) return "unchecked";
  if (selected.size === all.length) return "checked";
  return "indeterminate";
}

interface RefsPickerProps {
  catalog: RefsCatalog;
  value: RefsValue;
  onChange: (next: RefsValue) => void;
}

export function RefsPicker({ catalog, value, onChange }: RefsPickerProps) {
  // 子層 UI 用 Set<string> 表達「目前哪些被勾」；
  // `null`（全帶）→ 視為全部都勾。
  const groupSelections = {
    characters: groupToSet(value.characters, catalog.characters),
    clues: groupToSet(value.clues, catalog.clues),
    scenes: groupToSet(value.scenes, catalog.scenes),
  };

  const [expanded, setExpanded] = useState<Record<Group, boolean>>({
    characters: false,
    clues: false,
    scenes: false,
  });

  const updateGroup = (group: Group, next: Set<string>) => {
    const all = catalog[group];
    onChange({
      ...value,
      [group]: normalizeGroup(next, all),
    });
  };

  const toggleParent = (group: Group) => {
    const all = catalog[group];
    if (all.length === 0) return;
    const state = computeTriState(groupSelections[group], all);
    // checked → unchecked；其餘 → checked。
    const next = state === "checked" ? new Set<string>() : new Set(all);
    updateGroup(group, next);
  };

  const toggleChild = (group: Group, name: string) => {
    const cur = new Set(groupSelections[group]);
    if (cur.has(name)) cur.delete(name);
    else cur.add(name);
    updateGroup(group, cur);
  };

  return (
    <div data-testid="refs-picker">
      <div className="px-2.5 py-1.5 text-[0.6875rem] font-semibold uppercase tracking-wider text-gray-500">
        參考來源
      </div>

      <SimpleRow
        label="世界觀"
        checked={value.overview}
        disabled={!catalog.hasOverview}
        disabledHint="尚未生成"
        onToggle={() => onChange({ ...value, overview: !value.overview })}
      />
      <SimpleRow
        label="風格"
        checked={value.style}
        onToggle={() => onChange({ ...value, style: !value.style })}
      />

      {GROUPS.map((group) => {
        const all = catalog[group];
        const selected = groupSelections[group];
        const state = computeTriState(selected, all);
        const isEmpty = all.length === 0;
        const isExpanded = expanded[group];
        return (
          <GroupRow
            key={group}
            label={GROUP_LABEL[group]}
            triState={state}
            count={`${selected.size}/${all.length}`}
            disabled={isEmpty}
            expanded={isExpanded}
            onToggleParent={() => toggleParent(group)}
            onToggleExpand={() =>
              !isEmpty &&
              setExpanded((prev) => ({ ...prev, [group]: !prev[group] }))
            }
          >
            {isExpanded && !isEmpty && (
              <div className="max-h-32 overflow-y-auto pl-7 pr-2 py-1">
                {all.map((name) => (
                  <ChildRow
                    key={name}
                    label={name}
                    checked={selected.has(name)}
                    onToggle={() => toggleChild(group, name)}
                  />
                ))}
              </div>
            )}
          </GroupRow>
        );
      })}
    </div>
  );
}

function groupToSet(value: string[] | null, all: string[]): Set<string> {
  if (value === null) return new Set(all);
  return new Set(value);
}

function SimpleRow({
  label,
  checked,
  disabled,
  disabledHint,
  onToggle,
}: {
  label: string;
  checked: boolean;
  disabled?: boolean;
  disabledHint?: string;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      onClick={() => !disabled && onToggle()}
      disabled={disabled}
      className="flex w-full items-center justify-between rounded-md px-2.5 py-1.5 text-left text-xs text-gray-300 transition-colors hover:bg-gray-800 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
    >
      <div className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={checked && !disabled}
          readOnly
          disabled={disabled}
          className={CHECKBOX_CLASS}
        />
        <span>{label}</span>
      </div>
      {disabled && disabledHint && (
        <span className="text-[0.625rem] text-gray-600">（{disabledHint}）</span>
      )}
    </button>
  );
}

function GroupRow({
  label,
  triState,
  count,
  disabled,
  expanded,
  onToggleParent,
  onToggleExpand,
  children,
}: {
  label: string;
  triState: TriState;
  count: string;
  disabled?: boolean;
  expanded: boolean;
  onToggleParent: () => void;
  onToggleExpand: () => void;
  children?: React.ReactNode;
}) {
  return (
    <div>
      <div className="flex items-center rounded-md px-1 py-1 text-xs text-gray-300 transition-colors hover:bg-gray-800">
        <button
          type="button"
          onClick={onToggleExpand}
          disabled={disabled}
          className="flex h-6 w-6 items-center justify-center rounded text-gray-500 hover:text-gray-300 disabled:cursor-not-allowed"
          aria-label={expanded ? "收合" : "展開"}
        >
          {expanded ? (
            <ChevronDown className="h-3.5 w-3.5" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5" />
          )}
        </button>
        <button
          type="button"
          onClick={onToggleParent}
          disabled={disabled}
          className="flex flex-1 items-center justify-between px-1 text-left disabled:cursor-not-allowed"
        >
          <div className="flex items-center gap-2">
            <TriCheckbox state={disabled ? "unchecked" : triState} />
            <span>{label}</span>
          </div>
          <span className="text-[0.625rem] text-gray-600">
            {disabled ? "（尚未生成）" : count}
          </span>
        </button>
      </div>
      {children}
    </div>
  );
}

function ChildRow({
  label,
  checked,
  onToggle,
}: {
  label: string;
  checked: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className="flex w-full items-center gap-2 rounded-md px-2 py-1 text-left text-xs text-gray-400 transition-colors hover:bg-gray-800 hover:text-white"
    >
      <input
        type="checkbox"
        checked={checked}
        readOnly
        className={CHECKBOX_CLASS}
      />
      <span className="truncate">{label}</span>
    </button>
  );
}

function TriCheckbox({ state }: { state: TriState }) {
  // 用 ref 設 DOM indeterminate 旗標（React 不直接支援 prop）
  const ref = useRef<HTMLInputElement | null>(null);
  useEffect(() => {
    if (ref.current) {
      ref.current.indeterminate = state === "indeterminate";
    }
  }, [state]);
  return (
    <input
      ref={ref}
      type="checkbox"
      checked={state === "checked"}
      readOnly
      className={CHECKBOX_CLASS}
    />
  );
}
