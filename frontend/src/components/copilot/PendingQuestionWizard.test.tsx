import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { PendingQuestion } from "@/types";
import { PendingQuestionWizard } from "./PendingQuestionWizard";

function makePendingQuestion(overrides: Partial<PendingQuestion> = {}): PendingQuestion {
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
      {
        header: "章節",
        question: "包含哪些部分？",
        multiSelect: true,
        options: [
          { label: "引言", description: "開場上下文" },
          { label: "結論", description: "總結收束" },
        ],
      },
    ],
    ...overrides,
  };
}

describe("PendingQuestionWizard", () => {
  it("renders only the current question and blocks next until answered", () => {
    render(
      <PendingQuestionWizard
        pendingQuestion={makePendingQuestion()}
        answeringQuestion={false}
        error={null}
        onSubmitAnswers={vi.fn()}
      />,
    );

    expect(screen.getByText("問題 1/2")).toBeInTheDocument();
    expect(screen.getByText("輸出格式是什麼？")).toBeInTheDocument();
    expect(screen.queryByText("包含哪些部分？")).not.toBeInTheDocument();

    const nextButton = screen.getByRole("button", { name: "下一題" });
    expect(nextButton).toBeDisabled();

    fireEvent.click(screen.getByLabelText("摘要"));
    expect(nextButton).toBeEnabled();

    fireEvent.click(nextButton);
    expect(screen.getByText("問題 2/2")).toBeInTheDocument();
    expect(screen.getByText("包含哪些部分？")).toBeInTheDocument();
    expect(screen.queryByText("輸出格式是什麼？")).not.toBeInTheDocument();
  });

  it("keeps answers when navigating backward", () => {
    render(
      <PendingQuestionWizard
        pendingQuestion={makePendingQuestion()}
        answeringQuestion={false}
        error={null}
        onSubmitAnswers={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByLabelText("詳細"));
    fireEvent.click(screen.getByRole("button", { name: "下一題" }));
    fireEvent.click(screen.getByRole("button", { name: "上一步" }));

    expect(screen.getByText("輸出格式是什麼？")).toBeInTheDocument();
    expect(screen.getByLabelText("詳細")).toBeChecked();
  });

  it("validates custom other answers and joins multi-select payloads", () => {
    const onSubmitAnswers = vi.fn();

    render(
      <PendingQuestionWizard
        pendingQuestion={makePendingQuestion({
          questions: [
            {
              header: "章節",
              question: "包含哪些部分？",
              multiSelect: true,
              options: [
                { label: "引言", description: "開場上下文" },
                { label: "結論", description: "總結收束" },
              ],
            },
          ],
        })}
        answeringQuestion={false}
        error={null}
        onSubmitAnswers={onSubmitAnswers}
      />,
    );

    fireEvent.click(screen.getByLabelText("引言"));
    fireEvent.click(screen.getByLabelText("其他"));

    const submitButton = screen.getByRole("button", { name: "完成並提交" });
    expect(submitButton).toBeDisabled();

    fireEvent.change(screen.getByPlaceholderText("請輸入其他內容"), {
      target: { value: "附錄" },
    });
    expect(submitButton).toBeEnabled();

    fireEvent.click(submitButton);

    expect(onSubmitAnswers).toHaveBeenCalledWith("q-1", {
      "包含哪些部分？": "引言, 附錄",
    });
  });

  it("can render an explicit button-only approval question without other input", () => {
    render(
      <PendingQuestionWizard
        pendingQuestion={makePendingQuestion({
          questions: [
            {
              header: "確認",
              question: "確定要開始生成第 1 集的影片嗎？",
              multiSelect: false,
              allowOther: false,
              options: [
                { label: "確認生成", description: "開始執行這個生成任務" },
                { label: "取消", description: "不要執行這個生成任務" },
              ],
            },
          ],
        })}
        answeringQuestion={false}
        error={null}
        onSubmitAnswers={vi.fn()}
      />,
    );

    expect(screen.getByLabelText("確認生成")).toBeInTheDocument();
    expect(screen.getByLabelText("取消")).toBeInTheDocument();
    expect(screen.queryByLabelText("其他")).not.toBeInTheDocument();
  });

  it("resets local wizard state when question_id changes", () => {
    const { rerender } = render(
      <PendingQuestionWizard
        pendingQuestion={makePendingQuestion()}
        answeringQuestion={false}
        error={null}
        onSubmitAnswers={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByLabelText("摘要"));
    fireEvent.click(screen.getByRole("button", { name: "下一題" }));
    expect(screen.getByText("包含哪些部分？")).toBeInTheDocument();

    rerender(
      <PendingQuestionWizard
        pendingQuestion={makePendingQuestion({ question_id: "q-2" })}
        answeringQuestion={false}
        error={null}
        onSubmitAnswers={vi.fn()}
      />,
    );

    expect(screen.getByText("輸出格式是什麼？")).toBeInTheDocument();
    expect(screen.queryByText("包含哪些部分？")).not.toBeInTheDocument();
    expect(screen.getByLabelText("摘要")).not.toBeChecked();
    expect(screen.getByRole("button", { name: "下一題" })).toBeDisabled();
  });

  it("keeps the action area visible by making question content scrollable", () => {
    render(
      <PendingQuestionWizard
        pendingQuestion={makePendingQuestion({
          questions: [
            {
              header: "超長問題",
              question: "這是一個很長的問題。".repeat(120),
              multiSelect: false,
              options: [
                { label: "繼續", description: "繼續處理" },
              ],
            },
          ],
        })}
        answeringQuestion={false}
        error={null}
        onSubmitAnswers={vi.fn()}
      />,
    );

    expect(screen.getByTestId("pending-question-scroll-area")).toHaveClass("overflow-y-auto");
    expect(screen.getByRole("button", { name: "完成並提交" })).toBeInTheDocument();
  });
});
