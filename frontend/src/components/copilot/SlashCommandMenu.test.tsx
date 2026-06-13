import { createRef } from "react";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useAssistantStore } from "@/stores/assistant-store";
import { SlashCommandMenu } from "./SlashCommandMenu";
import type { SlashCommandMenuHandle } from "./SlashCommandMenu";

const SKILLS = [
  { name: "manga-workflow", description: "完整工作流", scope: "project" as const, path: "/tmp/a" },
  { name: "generate-script", description: "用 Gemini 生成 JSON 劇本", scope: "project" as const, path: "/tmp/b" },
  { name: "generate-video", description: "用 Veo 生成影片片段", scope: "project" as const, path: "/tmp/c" },
];

describe("SlashCommandMenu", () => {
  const onSelect = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    useAssistantStore.setState({ skills: SKILLS });
  });

  it("renders all skills when filter is empty", () => {
    render(<SlashCommandMenu filter="" onSelect={onSelect} />);
    expect(screen.getByText(/manga-workflow/)).toBeInTheDocument();
    expect(screen.getByText(/generate-script/)).toBeInTheDocument();
    expect(screen.getByText(/generate-video/)).toBeInTheDocument();
  });

  it("filters skills by name", () => {
    render(<SlashCommandMenu filter="script" onSelect={onSelect} />);
    expect(screen.getByText(/generate-script/)).toBeInTheDocument();
    expect(screen.queryByText(/manga-workflow/)).not.toBeInTheDocument();
  });

  it("filters skills by Chinese label", () => {
    render(<SlashCommandMenu filter="劇本" onSelect={onSelect} />);
    expect(screen.getByText(/generate-script/)).toBeInTheDocument();
    expect(screen.queryByText(/manga-workflow/)).not.toBeInTheDocument();
  });

  it("returns null when no skills match", () => {
    const { container } = render(<SlashCommandMenu filter="nonexistent" onSelect={onSelect} />);
    expect(container.firstChild).toBeNull();
  });

  it("calls onSelect with command on mousedown", () => {
    render(<SlashCommandMenu filter="" onSelect={onSelect} />);
    fireEvent.mouseDown(screen.getByText(/manga-workflow/).closest("button")!);
    expect(onSelect).toHaveBeenCalledWith("/manga-workflow");
  });

  it("displays Chinese labels for known skills", () => {
    render(<SlashCommandMenu filter="" onSelect={onSelect} />);
    expect(screen.getByText("影片工作流程")).toBeInTheDocument();
    expect(screen.getByText("生成劇本")).toBeInTheDocument();
    expect(screen.getByText("生成影片")).toBeInTheDocument();
  });

  it("shows distinct icons per skill", () => {
    const { container } = render(<SlashCommandMenu filter="" onSelect={onSelect} />);
    const buttons = container.querySelectorAll("button");
    for (const btn of buttons) {
      expect(btn.querySelector("svg")).toBeTruthy();
    }
  });

  describe("keyboard navigation via imperative handle", () => {
    it("navigates down and selects with Enter", () => {
      const ref = createRef<SlashCommandMenuHandle>();
      render(<SlashCommandMenu ref={ref} filter="" onSelect={onSelect} />);

      // Initially first item is active
      const firstOption = screen.getByText(/manga-workflow/).closest("button")!;
      expect(firstOption).toHaveAttribute("aria-selected", "true");

      // Arrow down → second item
      act(() => { ref.current!.handleKeyDown("ArrowDown"); });
      const secondOption = screen.getByText(/generate-script/).closest("button")!;
      expect(secondOption).toHaveAttribute("aria-selected", "true");
      expect(firstOption).toHaveAttribute("aria-selected", "false");

      // Enter → select second item
      act(() => { ref.current!.handleKeyDown("Enter"); });
      expect(onSelect).toHaveBeenCalledWith("/generate-script");
    });

    it("selects the active command with Tab", () => {
      const ref = createRef<SlashCommandMenuHandle>();
      render(<SlashCommandMenu ref={ref} filter="" onSelect={onSelect} />);

      let consumed = false;
      act(() => {
        consumed = ref.current!.handleKeyDown("Tab");
      });

      expect(consumed).toBe(true);
      expect(onSelect).toHaveBeenCalledWith("/manga-workflow");
    });

    it("wraps around when navigating past boundaries", () => {
      const ref = createRef<SlashCommandMenuHandle>();
      render(<SlashCommandMenu ref={ref} filter="" onSelect={onSelect} />);

      // ArrowUp from first → wraps to last
      act(() => { ref.current!.handleKeyDown("ArrowUp"); });
      const lastOption = screen.getByText(/generate-video/).closest("button")!;
      expect(lastOption).toHaveAttribute("aria-selected", "true");
    });

    it("exposes activeDescendantId", () => {
      const ref = createRef<SlashCommandMenuHandle>();
      render(<SlashCommandMenu ref={ref} filter="" onSelect={onSelect} />);

      expect(ref.current!.activeDescendantId).toBe("slash-command-menu-option-0");
      act(() => { ref.current!.handleKeyDown("ArrowDown"); });
      expect(ref.current!.activeDescendantId).toBe("slash-command-menu-option-1");
    });
  });

  describe("generate-overview / generate-scenes skills", () => {
    const EXTRA_SKILLS = [
      ...SKILLS,
      { name: "generate-overview", description: "生成專案世界觀", scope: "project" as const, path: "/tmp/o" },
      { name: "generate-scenes", description: "生成場景圖", scope: "project" as const, path: "/tmp/s" },
    ];

    beforeEach(() => {
      useAssistantStore.setState({ skills: EXTRA_SKILLS });
    });

    it("renders both new skills in the menu", () => {
      render(<SlashCommandMenu filter="" onSelect={onSelect} />);
      expect(screen.getByText(/generate-overview/)).toBeInTheDocument();
      expect(screen.getByText(/generate-scenes/)).toBeInTheDocument();
    });

    it("shows fallback Chinese labels for the new skills", () => {
      render(<SlashCommandMenu filter="" onSelect={onSelect} />);
      expect(screen.getByText("生成世界觀")).toBeInTheDocument();
      expect(screen.getByText("生成場景")).toBeInTheDocument();
    });

    it("filters generate-overview by name", () => {
      render(<SlashCommandMenu filter="overview" onSelect={onSelect} />);
      expect(screen.getByText(/generate-overview/)).toBeInTheDocument();
      expect(screen.queryByText(/generate-scenes/)).not.toBeInTheDocument();
    });

    it("filters generate-scenes by Chinese fallback label", () => {
      render(<SlashCommandMenu filter="場景" onSelect={onSelect} />);
      expect(screen.getByText(/generate-scenes/)).toBeInTheDocument();
      expect(screen.queryByText(/generate-overview/)).not.toBeInTheDocument();
    });

    it("inserts the correct command when a new skill is picked", () => {
      render(<SlashCommandMenu filter="overview" onSelect={onSelect} />);
      fireEvent.mouseDown(screen.getByText(/generate-overview/).closest("button")!);
      expect(onSelect).toHaveBeenCalledWith("/generate-overview");
    });
  });
});
