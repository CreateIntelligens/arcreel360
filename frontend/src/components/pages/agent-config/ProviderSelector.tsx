// 執行階段供應商選擇器：包含 grid + 描述卡。

import { AssistantRuntimeGrid } from "./AssistantRuntimeGrid";
import { SectionHeading } from "./shared";
import { ASSISTANT_PROVIDER_META, DEFAULT_ASSISTANT_PROVIDERS, cardClassName } from "./constants";

export interface ProviderSelectorProps {
  available: string[] | undefined;
  value: string;
  onChange: (providerId: string) => void;
  saving: boolean;
}

export function ProviderSelector({ available, value, onChange, saving }: ProviderSelectorProps) {
  const providerMeta = ASSISTANT_PROVIDER_META[value] ?? ASSISTANT_PROVIDER_META.claude;
  return (
    <div>
      <SectionHeading
        title="執行階段供應商"
        description="選擇目前 AI Agent 使用的執行階段供應商；不同供應商支援的能力層級不同。"
      />

      <div className={`${cardClassName} space-y-4`}>
        <AssistantRuntimeGrid
          available={available ?? [...DEFAULT_ASSISTANT_PROVIDERS]}
          value={value}
          onChange={onChange}
          disabled={saving}
        />

        <div className="rounded-2xl border border-white/6 bg-black/12 px-4 py-4 text-sm text-[color:var(--wb-text-secondary)]">
          <div className="flex items-center gap-2 text-[color:var(--wb-text-primary)]">
            <span className="font-medium">{providerMeta.label}</span>
            <span className="rounded-full border border-white/6 px-2 py-0.5 text-xs uppercase tracking-wide text-[color:var(--wb-text-muted)]">
              {providerMeta.tier}
            </span>
          </div>
          <p className="mt-2 text-sm text-[color:var(--wb-text-secondary)]">{providerMeta.description}</p>
          <p className="mt-2 text-xs text-[color:var(--wb-text-muted)]">{providerMeta.requirement}</p>
        </div>
      </div>
    </div>
  );
}
