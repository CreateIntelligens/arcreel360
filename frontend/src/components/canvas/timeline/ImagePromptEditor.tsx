import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { AutoTextarea } from "@/components/ui/AutoTextarea";
import { CompactInput } from "@/components/ui/CompactInput";
import { DropdownPill } from "@/components/ui/DropdownPill";
import type { EntityMentionNames, EntityMentionSources } from "@/utils/entity-mentions";
import { SHOT_TYPES } from "@/types";
import type { ImagePrompt, ShotType } from "@/types";

interface ImagePromptEditorProps {
  prompt: ImagePrompt;
  onUpdate: (patch: Partial<ImagePrompt>) => void;
  entities?: EntityMentionSources;
  linkedNames?: EntityMentionNames;
}

/** Structured editor for ImagePrompt fields with collapsible composition section. */
export function ImagePromptEditor({
  prompt,
  onUpdate,
  entities,
  linkedNames,
}: ImagePromptEditorProps) {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className="flex flex-col gap-2">
      <AutoTextarea
        value={prompt.scene}
        onChange={(v) => onUpdate({ scene: v })}
        placeholder="分鏡圖描述..."
        entities={entities}
        linkedNames={linkedNames}
        className="max-h-32 overflow-y-auto"
      />

      {/* Collapsible composition fields */}
      <button
        type="button"
        onClick={() => setCollapsed((c) => !c)}
        className="inline-flex items-center gap-1 self-start text-[10px] text-gray-500 hover:text-gray-400"
      >
        <ChevronDown
          className={`h-3 w-3 transition-transform ${collapsed ? "-rotate-90" : ""}`}
        />
        構圖引數
      </button>

      {!collapsed && (
        <div className="flex flex-col gap-2 pl-1">
          <DropdownPill
            label="鏡頭"
            value={prompt.composition.shot_type}
            options={SHOT_TYPES}
            onChange={(v: ShotType) =>
              onUpdate({
                composition: { ...prompt.composition, shot_type: v },
              })
            }
          />
          <CompactInput
            label="光線"
            value={prompt.composition.lighting}
            onChange={(v) =>
              onUpdate({
                composition: { ...prompt.composition, lighting: v },
              })
            }
            placeholder="光線描述..."
          />
          <CompactInput
            label="氛圍"
            value={prompt.composition.ambiance}
            onChange={(v) =>
              onUpdate({
                composition: { ...prompt.composition, ambiance: v },
              })
            }
            placeholder="氛圍描述..."
          />
        </div>
      )}
    </div>
  );
}
