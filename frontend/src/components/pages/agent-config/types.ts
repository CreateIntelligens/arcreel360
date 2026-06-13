// Shared types for AgentConfigTab and its sub-components.

import type { SystemConfigPatch } from "@/types";

export interface AgentDraft {
  assistantProvider: string;
  anthropicKey: string;        // new API key input (empty = don't change)
  anthropicBaseUrl: string;    // in-place editing; empty = clear
  anthropicModel: string;      // in-place editing; empty = clear
  haikuModel: string;
  opusModel: string;
  sonnetModel: string;
  subagentModel: string;
  cleanupDelaySeconds: string;
  maxConcurrentSessions: string;
}

export type UpdateDraft = <K extends keyof AgentDraft>(key: K, value: AgentDraft[K]) => void;

export type ClearField = (fieldId: string, patch: SystemConfigPatch, label: string) => void | Promise<void>;
