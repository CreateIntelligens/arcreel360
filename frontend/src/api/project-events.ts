/**
 * 專案事件 SSE 流式。
 */

import { API_BASE, withAuthQuery } from "./_http";
import type { ProjectEventStreamOptions } from "./types";

export const projectEventsApi = {
  openProjectEventStream(
    options: ProjectEventStreamOptions,
  ): EventSource {
    const url = withAuthQuery(
      `${API_BASE}/projects/${encodeURIComponent(options.projectName)}/events/stream`,
    );
    const source = new EventSource(url);

    const parsePayload = (event: MessageEvent): unknown | null => {
      try {
        return JSON.parse(event.data || "{}");
      } catch (err) {
        console.error("解析專案事件 SSE 資料失敗:", err, event.data);
        return null;
      }
    };

    const createHandler = (
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      callback?: (payload: any, event: MessageEvent) => void,
    ) => {
      return (event: Event) => {
        if (typeof callback !== "function") return;
        const payload = parsePayload(event as MessageEvent);
        if (payload) {
          callback(payload, event as MessageEvent);
        }
      };
    };

    source.addEventListener("snapshot", createHandler(options.onSnapshot));
    source.addEventListener("changes", createHandler(options.onChanges));

    source.onerror = (event: Event) => {
      if (typeof options.onError === "function") {
        options.onError(event);
      }
    };

    return source;
  },
};
