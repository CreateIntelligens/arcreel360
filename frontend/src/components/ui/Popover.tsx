import { createPortal } from "react-dom";
import { useAnchoredPopover } from "@/hooks/useAnchoredPopover";
import { UI_LAYERS } from "@/utils/ui-layers";
import type { RefObject, ReactNode, CSSProperties } from "react";

// ---------------------------------------------------------------------------
// Popover — 統一彈出面板原語
// ---------------------------------------------------------------------------
// 所有彈出面板必須使用此元件，而非手動組合 createPortal + useAnchoredPopover。
// 它透過 portal 脫離父級層疊上下文（如 header 的 backdrop-blur），
// 保證背景不透明並統一 z-index 管理。

/** 面板預設背景色（gray-900 = rgb(17 24 39)） */
export const POPOVER_BG = "rgb(17 24 39)";

type PopoverAlign = "start" | "center" | "end";
export type PopoverLayer = keyof typeof UI_LAYERS;

interface PopoverProps {
  open: boolean;
  onClose?: () => void;
  anchorRef: RefObject<HTMLElement | null>;
  children: ReactNode;
  /** Tailwind width class, e.g. "w-72", "w-96" */
  width?: string;
  /** 額外 className（追加到面板根元素） */
  className?: string;
  /** 額外內聯樣式 */
  style?: CSSProperties;
  /** 錨點偏移量（px），預設 8 */
  sideOffset?: number;
  /** 對齊方式，預設 "end" */
  align?: PopoverAlign;
  /** z-index 層級，預設 "workspacePopover" */
  layer?: PopoverLayer;
  /** 自定義背景色，預設 POPOVER_BG */
  backgroundColor?: string;
}

export function Popover({
  open,
  onClose,
  anchorRef,
  children,
  width = "w-72",
  className = "",
  style,
  sideOffset = 8,
  align,
  layer = "workspacePopover",
  backgroundColor = POPOVER_BG,
}: PopoverProps) {
  const { panelRef, positionStyle } = useAnchoredPopover({
    open,
    anchorRef,
    onClose,
    sideOffset,
    align,
  });

  if (!open || typeof document === "undefined") return null;

  return createPortal(
    <div
      ref={panelRef}
      className={`fixed isolate ${width} ${UI_LAYERS[layer]} ${className}`}
      style={{
        ...positionStyle,
        backgroundColor,
        ...style,
      }}
    >
      {children}
    </div>,
    document.body,
  );
}
