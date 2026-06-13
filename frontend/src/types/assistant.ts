/**
 * Assistant / agent runtime type definitions.
 *
 * Maps to backend models in:
 * - webui/server/agent_runtime/models.py (SessionMeta, SessionStatus, AssistantSnapshotV2)
 * - webui/server/agent_runtime/turn_grouper.py (Turn, ContentBlock structure)
 * - webui/server/agent_runtime/service.py (SkillInfo, stream events)
 */

export type SessionStatus = "idle" | "running" | "completed" | "error" | "interrupted";

export type AssistantProviderTier = "lite" | "workflow-grade" | "full";

export interface AssistantProviderCapabilities {
  provider: string;
  tier: AssistantProviderTier;
  supports_streaming: boolean;
  supports_images: boolean;
  supports_tool_calls: boolean;
  supports_interrupt: boolean;
  supports_resume: boolean;
  supports_subagents: boolean;
  supports_permission_hooks: boolean;
}

export const ASSISTANT_PROVIDER_LABELS: Record<string, string> = {
  claude: "Claude · 工作流模式",
  "gemini-lite": "Gemini · 對話模式",
  "gemini-full": "Gemini · 工作流模式",
  "openai-lite": "OpenAI · 對話模式",
  "openai-full": "OpenAI · 工作流模式",
};

// Capabilities 由後端權威下發（包含在 session list / get / SSE event 的 capabilities 欄位中）。
// fallback 用於後端 capabilities 還沒到達(首屏 / 切 provider 後新建會話的瞬間)。
// 根據 provider id 推 tier:`*-full` 與 `claude` 是工作流 full,其餘 lite。
// 一旦後端 SSE event 攜帶 capabilities,本 fallback 會被覆蓋。
const FULL_TIER_PROVIDERS = new Set(["claude", "gemini-full", "openai-full"]);

function fallbackCapabilitiesForProvider(provider: string): AssistantProviderCapabilities {
  const isFull = FULL_TIER_PROVIDERS.has(provider);
  return {
    provider,
    tier: isFull ? "full" : "lite",
    supports_streaming: true,
    supports_images: true,
    supports_tool_calls: isFull,
    supports_interrupt: true,
    supports_resume: true,
    supports_subagents: isFull,
    supports_permission_hooks: isFull,
  };
}

export function inferAssistantProvider(sessionId?: string | null): string {
  if (!sessionId) return "gemini-lite";
  // gemini-full 前綴必須先匹配，否則會被 "gemini:" 吃掉
  if (sessionId.startsWith("gemini-full:")) return "gemini-full";
  if (sessionId.startsWith("gemini:")) return "gemini-lite";
  if (sessionId.startsWith("openai-full:")) return "openai-full";
  if (sessionId.startsWith("openai:")) return "openai-lite";
  return "claude";
}

export function resolveAssistantCapabilities(
  sessionLike?: Pick<SessionMeta, "id" | "provider" | "capabilities"> | null,
  fallbackProvider?: string | null,
): AssistantProviderCapabilities {
  if (sessionLike?.capabilities) return sessionLike.capabilities;
  const provider = sessionLike?.provider || fallbackProvider || inferAssistantProvider(sessionLike?.id);
  return fallbackCapabilitiesForProvider(provider);
}

export interface SessionMeta {
  id: string;              // 現在就是 sdk_session_id
  provider?: string;
  capabilities?: AssistantProviderCapabilities;
  project_name: string;
  title: string;
  status: SessionStatus;
  created_at: string;
  updated_at: string;
}

export interface ContentBlock {
  type: "text" | "thinking" | "tool_use" | "tool_result" | "skill_content" | "task_progress" | "interrupt_notice" | "image";
  text?: string;
  thinking?: string;
  id?: string;
  name?: string;
  input?: Record<string, unknown>;
  result?: string;
  is_error?: boolean;
  skill_content?: string;
  tool_use_id?: string;
  content?: string;
  // image block fields
  source?: { type: "base64"; media_type: string; data: string };
  // task_progress fields
  task_id?: string;
  status?: string;
  description?: string;
  summary?: string;
  task_status?: string;
  usage?: { total_tokens?: number; tool_uses?: number; duration_ms?: number };
}

export interface Turn {
  type: "user" | "assistant" | "system";
  content: ContentBlock[];
  uuid?: string;
  timestamp?: string;
  subtype?: string;
}

export interface PendingQuestion {
  question_id: string;
  questions: Array<{
    header?: string;
    question: string;
    options: Array<{ label: string; description: string }>;
    multiSelect: boolean;
    allowOther?: boolean;
  }>;
}

export interface AssistantSnapshot {
  session_id: string;
  provider?: string;
  capabilities?: AssistantProviderCapabilities;
  status: SessionStatus;
  turns: Turn[];
  draft_turn: Turn | null;
  pending_questions: PendingQuestion[];
}

export interface SkillInfo {
  name: string;
  description: string;
  scope: "project" | "user";
  path: string;
  label?: string;
  icon?: string;
}

export interface TodoItem {
  content: string;
  activeForm: string;
  status: "pending" | "in_progress" | "completed";
}
