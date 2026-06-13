import { useEffect, useState } from "react";
import { API } from "@/api";

/** 全域預設模型（image/video/text），供各下拉的「跟隨全域」提示複用。 */
export interface GlobalModelDefaults {
  image: string;
  video: string;
  text: string;
}

const EMPTY: GlobalModelDefaults = { image: "", video: "", text: "" };

/**
 * 讀取系統全域預設模型。當某處下拉選「專案預設／跟隨全域」而專案本身未覆寫時，
 * 用這裡的值顯示「實際指向哪個模型」的提示。
 *
 * getSystemConfig 本身於 API 層快取，重複呼叫成本低；此 hook 僅做一次性讀取。
 */
export function useGlobalModelDefaults(): GlobalModelDefaults {
  const [defaults, setDefaults] = useState<GlobalModelDefaults>(EMPTY);

  useEffect(() => {
    let disposed = false;
    // 提示用途，非關鍵路徑：getSystemConfig 不可用或失敗時靜默維持空值。
    Promise.resolve()
      .then(() => API.getSystemConfig())
      .then((config) => {
        if (disposed) return;
        const s = config.settings;
        setDefaults({
          image: s?.default_image_backend ?? "",
          video: s?.default_video_backend ?? "",
          text: s?.default_text_backend ?? "",
        });
      })
      .catch(() => {});
    return () => {
      disposed = true;
    };
  }, []);

  return defaults;
}
