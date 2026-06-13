import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ContentBlock, TodoItem } from "@/types";
import { ToolCallWithResult } from "./ToolCallWithResult";

function makeTodo(
  content: string,
  status: TodoItem["status"] = "pending",
): TodoItem {
  return {
    content,
    activeForm: `正在處理${content}`,
    status,
  };
}

function makeTodoWriteBlock(overrides: Partial<ContentBlock> = {}): ContentBlock {
  return {
    type: "tool_use",
    id: "todo-write-1",
    name: "TodoWrite",
    input: {
      todos: [makeTodo("準備任務"), makeTodo("完成任務", "completed")],
    },
    ...overrides,
  };
}

describe("ToolCallWithResult", () => {
  it("keeps successful TodoWrite calls in the compact summary mode", () => {
    render(<ToolCallWithResult block={makeTodoWriteBlock({ result: "ok" })} />);

    expect(screen.getByText("任務清單 1/2 完成")).toBeInTheDocument();
    expect(screen.queryByText("執行失敗")).not.toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("shows the generic expandable error view for failed TodoWrite calls", () => {
    render(
      <ToolCallWithResult
        block={makeTodoWriteBlock({
          result: "permission denied",
          is_error: true,
        })}
      />,
    );

    fireEvent.click(screen.getByRole("button"));

    expect(screen.getByText("執行失敗")).toBeInTheDocument();
    expect(screen.getByText("permission denied")).toBeInTheDocument();
    expect(screen.queryByText("任務清單 1/2 完成")).not.toBeInTheDocument();
  });
});
