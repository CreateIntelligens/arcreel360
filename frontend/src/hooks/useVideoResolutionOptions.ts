import { useEffect, useMemo, useState } from "react";
import { API } from "@/api";
import {
  getProviderModels,
  lookupSupportedResolutions,
} from "@/utils/provider-models";
import type { ProviderInfo } from "@/types";

export function useVideoResolutionOptions(projectVideoBackend: string | null | undefined) {
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [globalVideoBackend, setGlobalVideoBackend] = useState("");

  useEffect(() => {
    let disposed = false;

    Promise.all([getProviderModels(), API.getSystemConfig()])
      .then(([providerList, config]) => {
        if (disposed) return;
        setProviders(providerList);
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
    return lookupSupportedResolutions(providers, backend);
  }, [globalVideoBackend, projectVideoBackend, providers]);
}
