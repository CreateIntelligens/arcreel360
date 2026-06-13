// Pure helpers for converting between API responses and the AgentDraft form state.

import type { GetSystemConfigResponse, SystemConfigPatch } from "@/types";
import type { AgentDraft } from "./types";

export function buildDraft(data: GetSystemConfigResponse): AgentDraft {
  const s = data.settings;
  return {
    assistantProvider: s.assistant_provider ?? "claude",
    anthropicKey: "",
    anthropicBaseUrl: s.anthropic_base_url ?? "",
    anthropicModel: s.anthropic_model ?? "",
    haikuModel: s.anthropic_default_haiku_model ?? "",
    opusModel: s.anthropic_default_opus_model ?? "",
    sonnetModel: s.anthropic_default_sonnet_model ?? "",
    subagentModel: s.claude_code_subagent_model ?? "",
    cleanupDelaySeconds: String(s.agent_session_cleanup_delay_seconds ?? 300),
    maxConcurrentSessions: String(s.agent_max_concurrent_sessions ?? 5),
  };
}

export function deepEqual(a: AgentDraft, b: AgentDraft): boolean {
  return (
    a.assistantProvider === b.assistantProvider &&
    a.anthropicKey === b.anthropicKey &&
    a.anthropicBaseUrl === b.anthropicBaseUrl &&
    a.anthropicModel === b.anthropicModel &&
    a.haikuModel === b.haikuModel &&
    a.opusModel === b.opusModel &&
    a.sonnetModel === b.sonnetModel &&
    a.subagentModel === b.subagentModel &&
    a.cleanupDelaySeconds === b.cleanupDelaySeconds &&
    a.maxConcurrentSessions === b.maxConcurrentSessions
  );
}

export function buildPatch(draft: AgentDraft, saved: AgentDraft): SystemConfigPatch {
  const patch: SystemConfigPatch = {};
  if (draft.assistantProvider !== saved.assistantProvider)
    patch.assistant_provider = draft.assistantProvider;
  if (draft.anthropicKey.trim()) patch.anthropic_api_key = draft.anthropicKey.trim();
  if (draft.anthropicBaseUrl !== saved.anthropicBaseUrl)
    patch.anthropic_base_url = draft.anthropicBaseUrl || "";
  if (draft.anthropicModel !== saved.anthropicModel)
    patch.anthropic_model = draft.anthropicModel || "";
  if (draft.haikuModel !== saved.haikuModel)
    patch.anthropic_default_haiku_model = draft.haikuModel || "";
  if (draft.opusModel !== saved.opusModel)
    patch.anthropic_default_opus_model = draft.opusModel || "";
  if (draft.sonnetModel !== saved.sonnetModel)
    patch.anthropic_default_sonnet_model = draft.sonnetModel || "";
  if (draft.subagentModel !== saved.subagentModel)
    patch.claude_code_subagent_model = draft.subagentModel || "";
  if (draft.cleanupDelaySeconds !== saved.cleanupDelaySeconds)
    patch.agent_session_cleanup_delay_seconds = Number(draft.cleanupDelaySeconds) || 300;
  if (draft.maxConcurrentSessions !== saved.maxConcurrentSessions)
    patch.agent_max_concurrent_sessions = Number(draft.maxConcurrentSessions) || 5;
  return patch;
}

export const EMPTY_DRAFT: AgentDraft = {
  assistantProvider: "claude",
  anthropicKey: "",
  anthropicBaseUrl: "",
  anthropicModel: "",
  haikuModel: "",
  opusModel: "",
  sonnetModel: "",
  subagentModel: "",
  cleanupDelaySeconds: "300",
  maxConcurrentSessions: "5",
};
