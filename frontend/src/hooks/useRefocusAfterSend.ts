import { useCallback, useEffect, useRef, type RefObject } from "react";

export function useRefocusAfterSend<T extends HTMLElement>(
  inputDisabled: boolean,
  targetRef: RefObject<T | null>,
) {
  const shouldRefocusAfterSendRef = useRef(false);

  const requestRefocusAfterSend = useCallback(() => {
    shouldRefocusAfterSendRef.current = true;
  }, []);

  useEffect(() => {
    if (inputDisabled || !shouldRefocusAfterSendRef.current) return;
    shouldRefocusAfterSendRef.current = false;
    targetRef.current?.focus();
  }, [inputDisabled, targetRef]);

  return requestRefocusAfterSend;
}
