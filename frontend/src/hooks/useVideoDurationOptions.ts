import { useEffect, useMemo, useState } from "react";
import { API } from "@/api";
import {
  getCustomProviderModels,
  getProviderModels,
  lookupDefaultResolution,
  lookupSupportedDurations,
  lookupVideoModelInfo,
  resolveVideoDurationOptions,
} from "@/utils/provider-models";
import type { CustomProviderInfo, ProviderInfo } from "@/types";

interface VideoDurationOptionsInput {
  currentResolution?: string | null;
  hasReferenceImage?: boolean;
}

export function useVideoDurationOptions(
  projectVideoBackend: string | null | undefined,
  options: VideoDurationOptionsInput = {},
) {
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [customProviders, setCustomProviders] = useState<CustomProviderInfo[]>([]);
  const [globalVideoBackend, setGlobalVideoBackend] = useState("");

  useEffect(() => {
    let disposed = false;

    Promise.all([getProviderModels(), getCustomProviderModels(), API.getSystemConfig()])
      .then(([providerList, customProviderList, config]) => {
        if (disposed) return;
        setProviders(providerList);
        setCustomProviders(customProviderList);
        setGlobalVideoBackend(config.settings?.default_video_backend ?? "");
      })
      .catch(() => {});

    return () => {
      disposed = true;
    };
  }, []);

  return useMemo(() => {
    const backend = projectVideoBackend || globalVideoBackend;
    if (!backend) return undefined;
    const model = lookupVideoModelInfo(providers, backend);
    const fallbackDurations = lookupSupportedDurations(providers, backend, customProviders);
    const currentResolution = options.currentResolution ?? lookupDefaultResolution(backend);
    return resolveVideoDurationOptions(model, fallbackDurations, {
      currentResolution,
      hasReferenceImage: options.hasReferenceImage,
    });
  }, [
    customProviders,
    globalVideoBackend,
    options.currentResolution,
    options.hasReferenceImage,
    projectVideoBackend,
    providers,
  ]);
}
