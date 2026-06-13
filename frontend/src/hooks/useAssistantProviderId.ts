import { useEffect, useState } from "react";
import { API } from "@/api";

const DEFAULT_ASSISTANT_PROVIDER_ID = "claude";

export function useAssistantProviderId() {
  const [activeProviderId, setActiveProviderId] = useState(DEFAULT_ASSISTANT_PROVIDER_ID);

  useEffect(() => {
    let cancelled = false;

    API.getSystemConfig()
      .then((data) => {
        if (!cancelled) {
          setActiveProviderId(data.settings.assistant_provider ?? DEFAULT_ASSISTANT_PROVIDER_ID);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setActiveProviderId(DEFAULT_ASSISTANT_PROVIDER_ID);
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return activeProviderId;
}
