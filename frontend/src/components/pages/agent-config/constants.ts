// Static configuration & style constants shared across the AgentConfigTab tree.

import type { SystemConfigPatch } from "@/types";
import type { AgentDraft } from "./types";

export const cardClassName = "workbench-panel rounded-[1.2rem] p-5";
export const inputClassName =
  "workbench-input w-full rounded-xl px-3 py-2.5 text-sm focus:outline-none";
export const smallBtnClassName =
  "rounded p-1 text-[color:var(--wb-text-dim)] hover:text-[color:var(--wb-text-secondary)] focus-visible:outline-none";

// Small inline clear button shown next to "當前：" when a value is set
export const inlineClearClassName =
  "ml-1.5 inline-flex items-center rounded p-0.5 text-[color:var(--wb-text-dim)] transition-colors hover:text-[color:var(--wb-danger)] disabled:cursor-not-allowed disabled:opacity-50";

// Model routing config — static, hoisted to module level to avoid re-creation on each render
export const MODEL_ROUTING_FIELDS: ReadonlyArray<{
  key: keyof AgentDraft;
  label: string;
  envVar: string;
  hint: string;
  patchKey: keyof SystemConfigPatch;
}> = [
  {
    key: "haikuModel",
    label: "Haiku 模型",
    envVar: "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    hint: "輕量任務（分類、提取、簡單問答）",
    patchKey: "anthropic_default_haiku_model",
  },
  {
    key: "sonnetModel",
    label: "Sonnet 模型",
    envVar: "ANTHROPIC_DEFAULT_SONNET_MODEL",
    hint: "均衡任務（寫作、編排、多步推理）",
    patchKey: "anthropic_default_sonnet_model",
  },
  {
    key: "opusModel",
    label: "Opus 模型",
    envVar: "ANTHROPIC_DEFAULT_OPUS_MODEL",
    hint: "複雜任務（長文創作、深度分析）",
    patchKey: "anthropic_default_opus_model",
  },
  {
    key: "subagentModel",
    label: "子 Agent 模型",
    envVar: "CLAUDE_CODE_SUBAGENT_MODEL",
    hint: "Subagent 平行執行時使用的模型",
    patchKey: "claude_code_subagent_model",
  },
] as const;

export const ASSISTANT_PROVIDER_META: Record<
  string,
  { label: string; tier: string; description: string; requirement: string }
> = {
  claude: {
    label: "Claude · 工作流模式",
    tier: "full",
    description: "Claude Agent SDK 工作流：可呼叫工具、生成劇本／分鏡／角色等。",
    requirement: "需要 Claude Code bundled CLI 與 OAuth 登入態。",
  },
  "gemini-lite": {
    label: "Gemini · 對話模式",
    tier: "lite",
    description: "純文字流式對話，輕量、低延遲；不會呼叫工具自動化。",
    requirement: "需要設定可用的 Gemini 文字供應商。",
  },
  "gemini-full": {
    label: "Gemini · 工作流模式",
    tier: "full",
    description: "Gemini function calling 工具循環：可自動化生成劇本／角色／線索並讀寫專案內檔案。",
    requirement: "需要 AI Studio API Key 並在系統配置中設好 Gemini 文字後端。",
  },
  "openai-lite": {
    label: "OpenAI · 對話模式",
    tier: "lite",
    description: "OpenAI 相容文字後端，純對話模式。",
    requirement: "需要設定可用的 OpenAI 文字供應商。",
  },
  "openai-full": {
    label: "OpenAI · 工作流模式",
    tier: "full",
    description: "OpenAI Agents SDK 工具循環：可呼叫 7 個 ArcReel skill 與專案檔案工具。",
    requirement: "需要設定 OpenAI API Key，並在系統配置中設好 OpenAI 文字後端。",
  },
};

export const DEFAULT_ASSISTANT_PROVIDERS = [
  "claude",
  "gemini-lite",
  "gemini-full",
  "openai-lite",
  "openai-full",
] as const;
