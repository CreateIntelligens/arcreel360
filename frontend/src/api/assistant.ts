/**
 * 助手會話 API + SSE 串流。
 */

import type { AssistantSnapshot, SessionMeta, SkillInfo } from "@/types";
import { API_BASE, withAuthQuery , getApi} from "./_http";
import type { SuccessResponse } from "./types";

function assistantBase(projectName: string): string {
  return `/projects/${encodeURIComponent(projectName)}/assistant`;
}

export const assistantApi = {
  async listAssistantSessions(
    projectName: string,
    status: string | null = null,
  ): Promise<{ sessions: SessionMeta[] }> {
    const params = new URLSearchParams();
    if (status) params.append("status", status);
    const query = params.toString();
    return getApi().request(
      `${assistantBase(projectName)}/sessions${query ? "?" + query : ""}`,
    );
  },

  async getAssistantSession(
    projectName: string,
    sessionId: string,
  ): Promise<{ session: SessionMeta }> {
    return getApi().request(
      `${assistantBase(projectName)}/sessions/${encodeURIComponent(sessionId)}`,
    );
  },

  async getAssistantSnapshot(
    projectName: string,
    sessionId: string,
  ): Promise<AssistantSnapshot> {
    return getApi().request(
      `${assistantBase(projectName)}/sessions/${encodeURIComponent(sessionId)}/snapshot`,
    );
  },

  async sendAssistantMessage(
    projectName: string,
    content: string,
    sessionId?: string | null,
    images?: Array<{ data: string; media_type: string }>,
  ): Promise<{ session_id: string; status: string }> {
    return getApi().request(`${assistantBase(projectName)}/sessions/send`, {
      method: "POST",
      body: JSON.stringify({
        content,
        session_id: sessionId || undefined,
        images: images || [],
      }),
    });
  },

  async interruptAssistantSession(
    projectName: string,
    sessionId: string,
  ): Promise<SuccessResponse> {
    return getApi().request(
      `${assistantBase(projectName)}/sessions/${encodeURIComponent(sessionId)}/interrupt`,
      { method: "POST" },
    );
  },

  async answerAssistantQuestion(
    projectName: string,
    sessionId: string,
    questionId: string,
    answers: Record<string, string>,
  ): Promise<SuccessResponse> {
    return getApi().request(
      `${assistantBase(projectName)}/sessions/${encodeURIComponent(sessionId)}/questions/${encodeURIComponent(questionId)}/answer`,
      {
        method: "POST",
        body: JSON.stringify({ answers }),
      },
    );
  },

  getAssistantStreamUrl(projectName: string, sessionId: string): string {
    return withAuthQuery(
      `${API_BASE}${assistantBase(projectName)}/sessions/${encodeURIComponent(sessionId)}/stream`,
    );
  },

  async listAssistantSkills(
    projectName: string,
  ): Promise<{ skills: SkillInfo[] }> {
    return getApi().request(`${assistantBase(projectName)}/skills`);
  },

  async deleteAssistantSession(
    projectName: string,
    sessionId: string,
  ): Promise<SuccessResponse> {
    return getApi().request(
      `${assistantBase(projectName)}/sessions/${encodeURIComponent(sessionId)}`,
      { method: "DELETE" },
    );
  },
};
