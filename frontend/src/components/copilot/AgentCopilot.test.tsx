import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { API } from "@/api";
import { useAssistantSession } from "@/hooks/useAssistantSession";
import { useAppStore } from "@/stores/app-store";
import { useAssistantStore } from "@/stores/assistant-store";
import { useProjectsStore } from "@/stores/projects-store";
import { ConfirmProvider } from "@/components/ui/ConfirmProvider";
import { UI_LAYERS } from "@/utils/ui-layers";
import { AgentCopilot } from "./AgentCopilot";

vi.mock("@/hooks/useAssistantSession", () => ({
  useAssistantSession: vi.fn(),
}));

vi.mock("./ContextBanner", () => ({
  ContextBanner: () => <div data-testid="context-banner" />,
}));

vi.mock("./SlashCommandMenu", () => ({
  SlashCommandMenu: vi.fn(() => null),
}));

vi.mock("./chat/ChatMessage", () => ({
  ChatMessage: ({ message }: { message: { type: string } }) => (
    <div data-testid="chat-message">{message.type}</div>
  ),
}));

const mockedUseAssistantSession = vi.mocked(useAssistantSession);

function renderAgentCopilot() {
  return render(
    <ConfirmProvider>
      <AgentCopilot />
    </ConfirmProvider>,
  );
}

function makePendingQuestion() {
  return {
    question_id: "q-1",
    questions: [
      {
        header: "輸出",
        question: "輸出格式是什麼？",
        multiSelect: false,
        options: [
          { label: "摘要", description: "簡潔輸出" },
          { label: "詳細", description: "完整說明" },
        ],
      },
    ],
  };
}

describe("AgentCopilot", () => {
  const sendMessage = vi.fn();
  const answerQuestion = vi.fn();
  const interrupt = vi.fn();
  const createNewSession = vi.fn();
  const switchSession = vi.fn();
  const deleteSession = vi.fn();

  beforeEach(() => {
    useAssistantStore.setState(useAssistantStore.getInitialState(), true);
    useProjectsStore.setState(useProjectsStore.getInitialState(), true);
    useAppStore.setState(useAppStore.getInitialState(), true);
    vi.clearAllMocks();

    useProjectsStore.getState().setCurrentProject("demo", null);
    vi.spyOn(API, "getSystemConfig").mockResolvedValue({
      settings: {
        assistant_provider: "claude",
      },
      options: {},
    } as Awaited<ReturnType<typeof API.getSystemConfig>>);
    mockedUseAssistantSession.mockReturnValue({
      sendMessage,
      answerQuestion,
      interrupt,
      createNewSession,
      switchSession,
      deleteSession,
    });
  });

  it("renders the pending-question wizard and disables normal sending", () => {
    useAssistantStore.setState({
      pendingQuestion: makePendingQuestion(),
      skills: [{ name: "plan", description: "Plan", scope: "project", path: "/tmp/plan" }],
    });

    renderAgentCopilot();

    expect(screen.getByText("需要你的選擇")).toBeInTheDocument();
    expect(screen.getByLabelText("助理輸入")).toBeDisabled();
    expect(screen.getByLabelText("傳送訊息")).toBeDisabled();
    expect(screen.getByPlaceholderText("請先回答上方問題")).toBeInTheDocument();
  });

  it("submits wizard answers through answerQuestion", () => {
    useAssistantStore.setState({
      pendingQuestion: makePendingQuestion(),
    });

    renderAgentCopilot();

    fireEvent.click(screen.getByLabelText("摘要"));
    fireEvent.click(screen.getByRole("button", { name: "完成並提交" }));

    expect(answerQuestion).toHaveBeenCalledWith("q-1", {
      "輸出格式是什麼？": "摘要",
    });
  });

  it("keeps assistant root isolated and uses local popover layer for session history", () => {
    useAssistantStore.setState({
      sessions: [
        {
          id: "session-1",
          project_name: "demo",
          title: "目前會話",
          status: "idle",
          created_at: "2026-02-01T00:00:00Z",
          updated_at: "2026-02-01T00:00:00Z",
        },
      ],
      currentSessionId: "session-1",
    });

    const { container } = renderAgentCopilot();

    expect(container.firstElementChild).toHaveClass("isolate");

    fireEvent.click(screen.getByTitle("切換會話"));
    expect(document.querySelector(`.${UI_LAYERS.assistantLocalPopover}`)).toBeTruthy();
  });

  it("shows provider downgrade hint for lite providers", async () => {
    vi.spyOn(API, "getSystemConfig").mockResolvedValue({
      settings: {
        assistant_provider: "gemini-lite",
      },
      options: {},
    } as Awaited<ReturnType<typeof API.getSystemConfig>>);

    renderAgentCopilot();

    expect(
      await screen.findByText(
        "目前為「對話模式」，僅支援文字交流。如需 AI 自動化生成劇本／分鏡／角色，請切換為「工作流模式」。",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "前往設定" })).toBeInTheDocument();
  });

  it("refocuses the assistant input after a sent message finishes", async () => {
    renderAgentCopilot();

    const input = screen.getByLabelText("助理輸入");
    fireEvent.change(input, { target: { value: "繼續討論分鏡" } });
    fireEvent.click(screen.getByLabelText("傳送訊息"));

    expect(sendMessage).toHaveBeenCalledWith("繼續討論分鏡", undefined);

    input.blur();
    expect(input).not.toHaveFocus();

    await act(async () => {
      useAssistantStore.setState({ sending: true, sessionStatus: "running" });
    });
    expect(screen.getByLabelText("助理輸入")).toBeDisabled();

    await act(async () => {
      useAssistantStore.setState({ sending: false, sessionStatus: "completed" });
    });

    await waitFor(() => {
      expect(screen.getByLabelText("助理輸入")).toHaveFocus();
    });
  });
});
