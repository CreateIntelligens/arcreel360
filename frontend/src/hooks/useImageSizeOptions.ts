import { useEffect, useMemo, useState } from "react";
import { API } from "@/api";
import {
  getProviderModels,
  lookupSupportedImageSizes,
} from "@/utils/provider-models";
import type { ProviderInfo } from "@/types";

/**
 * Resolve the supported image-size options for the given image backend
 * ("provider/model"), falling back to the global default image backend.
 * Returns undefined when no model-specific sizes are declared, so callers
 * fall back to DEFAULT_IMAGE_SIZES.
 */
export function useImageSizeOptions(projectImageBackend: string | null | undefined) {
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [globalImageBackend, setGlobalImageBackend] = useState("");

  useEffect(() => {
    let disposed = false;

    Promise.all([getProviderModels(), API.getSystemConfig()])
      .then(([providerList, config]) => {
        if (disposed) return;
        setProviders(providerList);
        setGlobalImageBackend(config.settings?.default_image_backend ?? "");
      })
      .catch(() => {});

    return () => {
      disposed = true;
    };
  }, []);

  return useMemo(() => {
    const backend = projectImageBackend || globalImageBackend;
    if (!backend) return undefined;
    return lookupSupportedImageSizes(providers, backend);
  }, [globalImageBackend, projectImageBackend, providers]);
}
