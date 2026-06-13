import { Plus, X } from "lucide-react";
import type { Dialogue } from "@/types";

// Sentinel chosen so it cannot collide with a real character name (contains
// chars rejected by the rename validator: angle brackets).
const CUSTOM_SENTINEL = "<custom>";

interface DialogueListEditorProps {
  dialogue: Dialogue[];
  onChange: (dialogue: Dialogue[]) => void;
  /** Names of characters present in this segment/scene. Used as the speaker dropdown options. */
  speakerOptions?: string[];
}

/** Editable list of speaker/line dialogue pairs. */
export function DialogueListEditor({
  dialogue,
  onChange,
  speakerOptions,
}: DialogueListEditorProps) {
  const update = (index: number, patch: Partial<Dialogue>) => {
    const next = dialogue.map((d, i) =>
      i === index ? { ...d, ...patch } : d
    );
    onChange(next);
  };

  const remove = (index: number) => {
    onChange(dialogue.filter((_, i) => i !== index));
  };

  const add = () => {
    onChange([...dialogue, { speaker: "", line: "" }]);
  };

  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-[11px] text-gray-500">對話</span>

      {dialogue.map((d, i) => {
        const options = speakerOptions ?? [];
        const speakerKnown = !d.speaker || options.includes(d.speaker);
        const dropdownAvailable = options.length > 0 && speakerKnown;
        return (
        <div key={i} className="flex items-start gap-1.5">
          {dropdownAvailable ? (
            <select
              value={d.speaker}
              onChange={(e) => {
                if (e.target.value === CUSTOM_SENTINEL) {
                  update(i, { speaker: " " });  // 空字串 fallback 回 dropdown，加 space 強制 free-text 分支
                } else {
                  update(i, { speaker: e.target.value });
                }
              }}
              className="w-20 shrink-0 rounded bg-gray-800 border border-gray-700 px-1 py-1 text-xs text-indigo-400 focus:border-indigo-500 focus:outline-none"
            >
              <option value="" disabled>角色</option>
              {options.map((name) => (
                <option key={name} value={name}>{name}</option>
              ))}
              <option value={CUSTOM_SENTINEL}>自訂…</option>
            </select>
          ) : (
            <input
              type="text"
              value={d.speaker}
              onChange={(e) => update(i, { speaker: e.target.value })}
              placeholder="角色"
              className="w-20 shrink-0 rounded bg-gray-800 border border-gray-700 px-1.5 py-1 text-xs text-indigo-400 placeholder-gray-600 focus:border-indigo-500 focus:outline-none"
              title={options.length > 0 ? "自訂角色（不在出場名單內）" : undefined}
            />
          )}
          <input
            type="text"
            value={d.line}
            onChange={(e) => update(i, { line: e.target.value })}
            placeholder="臺詞"
            className="min-w-0 flex-1 rounded bg-gray-800 border border-gray-700 px-1.5 py-1 text-xs text-gray-200 placeholder-gray-600 focus:border-indigo-500 focus:outline-none"
          />
          <button
            type="button"
            onClick={() => remove(i)}
            className="shrink-0 rounded p-0.5 text-gray-600 hover:bg-gray-800 hover:text-red-400"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
        );
      })}

      <button
        type="button"
        onClick={add}
        className="inline-flex items-center gap-1 self-start rounded px-2 py-0.5 text-xs text-gray-500 hover:bg-gray-800 hover:text-gray-300"
      >
        <Plus className="h-3 w-3" />
        新增對話
      </button>
    </div>
  );
}
