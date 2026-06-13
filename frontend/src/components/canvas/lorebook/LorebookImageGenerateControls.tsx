import { GenerateButton } from "@/components/ui/GenerateButton";
import { ProviderModelSelect } from "@/components/ui/ProviderModelSelect";
import { modelSelectRowClasses } from "@/utils/model-select-row";
import { useGlobalModelDefaults } from "@/hooks/useGlobalModelDefaults";

interface LorebookImageGenerateControlsProps {
  value: string;
  onChange: (value: string) => Promise<void> | void;
  options?: string[];
  providerNames?: Record<string, string>;
  onGenerate: () => Promise<void> | void;
  loading?: boolean;
  label: string;
}

export function LorebookImageGenerateControls({
  value,
  onChange,
  options = [],
  providerNames = {},
  onGenerate,
  loading,
  label,
}: LorebookImageGenerateControlsProps) {
  const hasOptions = options.length > 0;
  const rowClasses = modelSelectRowClasses(hasOptions);
  const globalDefaults = useGlobalModelDefaults();

  return (
    <div className={`${rowClasses.container} w-full`}>
      {hasOptions && (
        <div className={rowClasses.select}>
          <ProviderModelSelect
            value={value}
            onChange={(next) => void onChange(next)}
            options={options}
            providerNames={providerNames}
            placeholder="選擇圖片模型..."
            allowDefault={true}
            defaultLabel="專案預設模型"
            defaultModelValue={globalDefaults.image}
            className="w-full text-xs"
            size="sm"
          />
        </div>
      )}
      <GenerateButton
        onClick={() => void onGenerate()}
        loading={loading}
        label={label}
        className={rowClasses.button}
      />
    </div>
  );
}
