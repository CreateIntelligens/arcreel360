import { describe, expect, it } from "vitest";
import { ASSISTANT_PROVIDER_LABELS, inferAssistantProvider } from "./assistant";

describe("assistant provider helpers", () => {
  it("labels OpenAI full runtime", () => {
    expect(ASSISTANT_PROVIDER_LABELS["openai-full"]).toBe("OpenAI · 工作流模式");
  });

  it("infers openai-full before openai-lite", () => {
    expect(inferAssistantProvider("openai-full:abc123")).toBe("openai-full");
    expect(inferAssistantProvider("openai:abc123")).toBe("openai-lite");
  });
});
