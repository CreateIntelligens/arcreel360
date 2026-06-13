export const STYLE_OPTIONS = [
  { value: "Photographic", label: "寫實攝影" },
  { value: "Anime", label: "動漫風格" },
  { value: "3D Animation", label: "3D 動畫" },
] as const;

export type ProjectStyle = (typeof STYLE_OPTIONS)[number]["value"];
