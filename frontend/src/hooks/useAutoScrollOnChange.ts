import { useEffect, useRef, type RefObject } from "react";

// 距離底部多少以內視為「使用者仍貼著底部」，串流時才繼續自動捲。
const STICK_THRESHOLD_PX = 80;

export function useAutoScrollOnChange<T extends HTMLElement>(
  targetRef: RefObject<T | null>,
  changeSignal: unknown,
) {
  // 記錄使用者是否仍貼著底部；主動往上滑時暫停自動捲。
  const stickToBottomRef = useRef(true);

  useEffect(() => {
    const target = targetRef.current;
    if (!target) return;

    const handleScroll = () => {
      const distanceFromBottom =
        target.scrollHeight - target.scrollTop - target.clientHeight;
      stickToBottomRef.current = distanceFromBottom <= STICK_THRESHOLD_PX;
    };

    target.addEventListener("scroll", handleScroll, { passive: true });
    return () => target.removeEventListener("scroll", handleScroll);
  }, [targetRef]);

  useEffect(() => {
    const target = targetRef.current;
    if (target && stickToBottomRef.current) {
      target.scrollTop = target.scrollHeight;
    }
  }, [changeSignal, targetRef]);
}
