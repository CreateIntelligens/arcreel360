import { useCallback, useEffect, useMemo, useState } from "react";
import { RefreshCw } from "lucide-react";
import type { ProjectOverview } from "@/types";
import { API } from "@/api";
import { useAppStore } from "@/stores/app-store";
import { useGlobalModelDefaults } from "@/hooks/useGlobalModelDefaults";
import { ProviderModelSelect } from "@/components/ui/ProviderModelSelect";

/** 四個世界觀欄位的鍵;順序即畫面渲染順序(短欄位在前)。 */
const OVERVIEW_FIELDS = ["genre", "theme", "synopsis", "world_setting"] as const;
type OverviewField = (typeof OVERVIEW_FIELDS)[number];
type OverviewDraft = Record<OverviewField, string>;
type FieldMeta = {
  label: string;
  placeholder: string;
  multiline: boolean;
  rows?: number;
};

/** 把 overview 物件轉成純字串草稿,缺欄位以空字串補上。 */
function toDraft(overview: ProjectOverview | null | undefined): OverviewDraft {
  return {
    synopsis: overview?.synopsis ?? "",
    genre: overview?.genre ?? "",
    theme: overview?.theme ?? "",
    world_setting: overview?.world_setting ?? "",
  };
}

const FIELD_META: Record<OverviewField, FieldMeta> = {
  synopsis: {
    label: "故事梗概",
    placeholder: "用一段話描述整個故事的主線與走向。",
    multiline: true,
    rows: 4,
  },
  genre: {
    label: "題材類型",
    placeholder: "例如:古裝懸疑、都市奇幻。",
    multiline: false,
  },
  theme: {
    label: "核心主題",
    placeholder: "例如:救贖、成長、復仇。",
    multiline: false,
  },
  world_setting: {
    label: "世界觀設定",
    placeholder: "描述時代背景、世界規則、地理或社會環境。",
    multiline: true,
    rows: 5,
  },
};

const FOCUS_RING =
  "focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500";

function pushToast(message: string, tone: "success" | "error") {
  useAppStore.getState().pushToast(message, tone);
}

interface OverviewSectionProps {
  readonly projectName: string;
  readonly overview: ProjectOverview | null | undefined;
  /** 生成或手動儲存成功後,通知父層刷新專案資料。 */
  readonly onRefresh: () => Promise<void> | void;
  readonly textModelOptions?: string[];
  readonly providerNames?: Record<string, string>;
}

/**
 * 專案概述/世界觀區塊 — 支援手動編輯四個欄位與 AI 生成。
 * 編輯採「草稿 + 髒值偵測」模式:只有改動過才顯示儲存按鈕。
 */
export function OverviewSection({
  projectName,
  overview,
  onRefresh,
  textModelOptions = [],
  providerNames = {},
}: OverviewSectionProps) {
  const [draft, setDraft] = useState<OverviewDraft>(() => toDraft(overview));
  const [saving, setSaving] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [overviewModel, setOverviewModel] = useState("");
  const globalDefaults = useGlobalModelDefaults();
  const [overviewInstruction, setOverviewInstruction] = useState("");

  // 外部 overview 變動(例如生成完成)時,同步草稿。
  useEffect(() => {
    setDraft(toDraft(overview));
  }, [overview]);

  const dirtyFields = useMemo(() => {
    const base = toDraft(overview);
    return OVERVIEW_FIELDS.filter((field) => draft[field] !== base[field]);
  }, [draft, overview]);
  const isDirty = dirtyFields.length > 0;

  const handleChange = useCallback((field: OverviewField, value: string) => {
    setDraft((prev) => ({ ...prev, [field]: value }));
  }, []);

  const handleSave = useCallback(async () => {
    if (saving || dirtyFields.length === 0) return;
    setSaving(true);
    try {
      const patch: Partial<ProjectOverview> = {};
      for (const field of dirtyFields) {
        patch[field] = draft[field].trim();
      }
      await API.updateOverview(projectName, patch);
      await onRefresh();
      pushToast("專案概述已儲存", "success");
    } catch (err) {
      pushToast(`儲存失敗: ${(err as Error).message}`, "error");
    } finally {
      setSaving(false);
    }
  }, [saving, dirtyFields, draft, projectName, onRefresh]);

  const handleRegenerate = useCallback(async () => {
    if (regenerating) return;
    setRegenerating(true);
    try {
      await API.generateOverview(projectName, {
        model: overviewModel || null,
        instruction: overviewInstruction.trim() || null,
      });
      await onRefresh();
      pushToast("專案概述已生成", "success");
    } catch (err) {
      pushToast(`生成失敗: ${(err as Error).message}`, "error");
    } finally {
      setRegenerating(false);
    }
  }, [regenerating, projectName, overviewModel, overviewInstruction, onRefresh]);

  const hasOverview = Boolean(overview);

  return (
    <section className="space-y-3 rounded-xl border border-gray-800 bg-gray-900 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-0.5">
          <h3 className="text-sm font-semibold text-gray-300">專案概述</h3>
          <p className="text-xs text-gray-500">
            可直接編輯各欄位手動校準,或用 AI 依來源內容生成。
          </p>
        </div>
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          {textModelOptions.length > 0 && (
            <ProviderModelSelect
              value={overviewModel}
              options={textModelOptions}
              providerNames={providerNames}
              onChange={setOverviewModel}
              allowDefault
              defaultLabel="選擇模型"
              defaultModelValue={globalDefaults.text}
              placeholder="文字模型"
              aria-label="概述文字模型"
              className="w-52"
              size="sm"
            />
          )}
          <button
            type="button"
            onClick={() => void handleRegenerate()}
            disabled={regenerating}
            className={`flex shrink-0 items-center gap-1 rounded-md px-2 py-1 text-xs text-gray-400 transition-colors hover:bg-gray-800 hover:text-gray-200 disabled:cursor-not-allowed disabled:opacity-50 ${FOCUS_RING}`}
            title={hasOverview ? "生成概述" : "生成概述"}
          >
            <RefreshCw className={`h-3 w-3 ${regenerating ? "animate-spin" : ""}`} />
            <span>
              {regenerating ? "生成中..." : hasOverview ? "生成" : "生成概述"}
            </span>
          </button>
        </div>
      </div>

      <div>
        <label htmlFor="overview-generation-instruction" className="mb-1 block text-xs font-medium text-gray-400">
          概述生成提示詞
        </label>
        <textarea
          id="overview-generation-instruction"
          value={overviewInstruction}
          onChange={(e) => setOverviewInstruction(e.target.value)}
          rows={2}
          placeholder="例如：偏黑色幽默、強調女主復仇動機、世界觀要更殘酷。"
          className={`w-full rounded-lg border border-gray-700 bg-gray-800/80 px-3 py-2 text-sm leading-relaxed text-gray-200 placeholder-gray-500 ${FOCUS_RING} focus-visible:border-indigo-500`}
        />
      </div>

      {!hasOverview && (
        <p className="text-sm text-gray-500">
          尚未生成專案概述。點選右上角「生成概述」依來源內容自動生成,
          或直接在下方欄位手動填寫;有概述後製作流程才會往下推進。
        </p>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        {OVERVIEW_FIELDS.map((field) => {
          const meta = FIELD_META[field];
          const inputId = `overview-${field}`;
          return (
            <div
              key={field}
              className={meta.multiline ? "sm:col-span-2" : "sm:col-span-1"}
            >
              <label
                htmlFor={inputId}
                className="mb-1 block text-xs font-medium text-gray-400"
              >
                {meta.label}
              </label>
              {meta.multiline ? (
                <textarea
                  id={inputId}
                  value={draft[field]}
                  onChange={(e) => handleChange(field, e.target.value)}
                  rows={meta.rows}
                  placeholder={meta.placeholder}
                  className={`w-full rounded-lg border border-gray-700 bg-gray-800/80 px-3 py-2 text-sm leading-relaxed text-gray-200 placeholder-gray-500 ${FOCUS_RING} focus-visible:border-indigo-500`}
                />
              ) : (
                <input
                  id={inputId}
                  type="text"
                  value={draft[field]}
                  onChange={(e) => handleChange(field, e.target.value)}
                  placeholder={meta.placeholder}
                  className={`w-full rounded-lg border border-gray-700 bg-gray-800/80 px-3 py-2 text-sm text-gray-200 placeholder-gray-500 ${FOCUS_RING} focus-visible:border-indigo-500`}
                />
              )}
            </div>
          );
        })}
      </div>

      {isDirty && (
        <div className="flex items-center justify-end gap-3">
          <span className="text-xs text-gray-500">尚有未儲存的修改</span>
          <button
            type="button"
            onClick={() => void handleSave()}
            disabled={saving}
            className={`rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50 ${FOCUS_RING}`}
          >
            {saving ? "儲存中..." : "儲存概述"}
          </button>
        </div>
      )}
    </section>
  );
}
