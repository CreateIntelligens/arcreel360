import type { KeyboardEventHandler, MouseEvent, ReactNode } from "react";
import { UI_LAYERS } from "@/utils/ui-layers";

interface ModalProps {
  children: ReactNode;
  className?: string;
  onBackdropClick?: () => void;
  onKeyDown?: KeyboardEventHandler<HTMLDivElement>;
}

export function Modal({
  children,
  className,
  onBackdropClick,
  onKeyDown,
}: ModalProps) {
  const handleClick = (event: MouseEvent<HTMLDivElement>) => {
    if (event.target === event.currentTarget) {
      onBackdropClick?.();
    }
  };

  return (
    <div
      className={[
        `fixed inset-0 ${UI_LAYERS.modal} flex items-center justify-center bg-black/65 px-4`,
        className,
      ].filter(Boolean).join(" ")}
      onClick={onBackdropClick ? handleClick : undefined}
      onKeyDown={onKeyDown}
    >
      {children}
    </div>
  );
}
