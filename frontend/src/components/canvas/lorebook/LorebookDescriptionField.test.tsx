import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { LorebookDescriptionField } from "./LorebookDescriptionField";

describe("LorebookDescriptionField", () => {
  it("lays out the text model selector and generate button on a single row", () => {
    render(
      <LorebookDescriptionField
        value=""
        onChange={vi.fn()}
        placeholder="輸入描述"
        onGenerateAI={vi.fn()}
        textModel={null}
        onTextModelChange={vi.fn()}
        textModelOptions={["openai/gpt-4.1-mini", "gemini-aistudio/gemini-2.5-pro-preview-06-05"]}
        providerNames={{ openai: "OpenAI", "gemini-aistudio": "Gemini AI Studio" }}
      />,
    );

    const generateButton = screen.getByRole("button", { name: "生成描述" });
    const controls = generateButton.parentElement;
    if (!controls) throw new Error("missing description controls");

    expect(controls).toHaveClass("grid");
    expect(controls).toHaveClass("grid-cols-3");
    expect(controls).not.toHaveClass("flex-col");
    expect(controls.firstElementChild).toHaveClass("col-span-2");
    expect(generateButton).toHaveClass("col-span-1");
  });
});
