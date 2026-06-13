import type { ComponentProps, ReactNode } from "react";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SegmentCard } from "./SegmentCard";
import { API } from "@/api";
import { useAppStore } from "@/stores/app-store";
import { useCostStore } from "@/stores/cost-store";
import { useVideoDurationOptions } from "@/hooks/useVideoDurationOptions";
import type { SegmentCost } from "@/types";
import type { DramaScene, NarrationSegment } from "@/types";

vi.mock("@/hooks/useVideoDurationOptions", () => ({
  useVideoDurationOptions: vi.fn(),
}));

vi.mock("@/components/canvas/timeline/VersionTimeMachine", () => ({
  VersionTimeMachine: () => <div data-testid="version-time-machine">versions</div>,
}));

vi.mock("@/components/ui/AvatarStack", () => ({
  AvatarStack: ({ names }: { names: string[] }) => (
    <div data-testid="avatar-stack">{names.join(",")}</div>
  ),
}));

vi.mock("@/components/ui/ImageFlipReveal", () => ({
  ImageFlipReveal: ({
    src,
    alt,
    className,
    fallback,
  }: {
    src: string | null;
    alt: string;
    className?: string;
    fallback?: ReactNode;
  }) =>
    src ? <img src={src} alt={alt} className={className} /> : <>{fallback}</>,
}));

function makeSegment(overrides: Partial<NarrationSegment> = {}): NarrationSegment {
  return {
    segment_id: "SEG-1",
    episode: 1,
    duration_seconds: 4,
    segment_break: false,
    novel_text: "在雨夜裡抬頭。",
    characters_in_segment: ["Hero"],
    clues_in_segment: [],
    scene_in_segment: null,
    image_prompt: "一張電影感分鏡圖",
    video_prompt: "鏡頭緩慢推進",
    transition_to_next: "cut",
    generated_assets: {
      storyboard_image: "storyboards/SEG-1.png",
      video_clip: "videos/SEG-1.mp4",
      video_thumbnail: null,
      video_uri: null,
      status: "completed",
    },
    ...overrides,
  };
}

function makeDramaScene(overrides: Partial<DramaScene> = {}): DramaScene {
  return {
    scene_id: "SC-1",
    duration_seconds: 8,
    segment_break: false,
    scene_type: "劇情",
    characters_in_scene: ["Hero"],
    clues_in_scene: ["Key"],
    scene_in_scene: "古城",
    image_prompt: "一張電影感分鏡圖",
    video_prompt: {
      action: "角色抵達場景",
      camera_motion: "Static",
      ambiance_audio: "風聲",
      dialogue: [
        { speaker: "Hero", line: "抵達 @古城，看見 @Key。" },
      ],
    },
    transition_to_next: "cut",
    generated_assets: {
      storyboard_image: null,
      video_clip: null,
      video_thumbnail: null,
      video_uri: null,
      status: "pending",
    },
    ...overrides,
  };
}

type SegmentCardProps = ComponentProps<typeof SegmentCard>;

function renderSegmentCard(overrides: Partial<SegmentCardProps> = {}) {
  const props: SegmentCardProps = {
    segment: makeSegment(),
    contentMode: "narration",
    aspectRatio: "16:9",
    characters: {},
    clues: {},
    projectName: "demo",
    ...overrides,
  };

  return render(<SegmentCard {...props} />);
}

function setSegmentCost(cost: Partial<SegmentCost> = {}) {
  const segmentCost: SegmentCost = {
    segment_id: "SEG-1",
    duration_seconds: 4,
    estimate: {
      image: { USD: 0.12 },
      video: { USD: 0.34 },
    },
    actual: {
      image: { USD: 0.02 },
      video: { USD: 0.03 },
    },
    ...cost,
  };
  useCostStore.setState({ _segmentIndex: new Map([["SEG-1", segmentCost]]) });
}

describe("SegmentCard", () => {
  beforeEach(() => {
    useAppStore.setState(useAppStore.getInitialState(), true);
    useCostStore.setState(useCostStore.getInitialState(), true);
    vi.restoreAllMocks();
    vi.mocked(useVideoDurationOptions).mockReturnValue(undefined);
  });

  it("shows an image fullscreen trigger and uses native video controls", () => {
    const { container } = renderSegmentCard();

    expect(
      screen.getByRole("button", { name: "SEG-1 分鏡圖 全屏預覽" }),
    ).toBeInTheDocument();

    const video = container.querySelector("video");
    expect(video).not.toBeNull();
    expect(video).toHaveAttribute("controls");
    expect(video).toHaveAttribute("preload", "metadata");
  }, 10_000);

  it("uses @mentions in narration text to update segment entities without saving markers", () => {
    const onUpdatePrompt = vi.fn();
    renderSegmentCard({
      segment: makeSegment({ clues_in_segment: [] }),
      characters: { Hero: { description: "hero" } },
      clues: {
        Key: { description: "key", importance: "major" },
      },
      onUpdatePrompt,
    });

    const source = screen.getByLabelText("原文");
    fireEvent.change(source, { target: { value: "@Hero 拿起 @Key。" } });
    fireEvent.blur(source);

    expect(onUpdatePrompt).toHaveBeenCalledWith(
      "SEG-1",
      "novel_text",
      "Hero 拿起 Key。",
      {
        characters_in_segment: ["Hero"],
        clues_in_segment: ["Key"],
      },
    );
  });

  it("highlights linked entity names in saved narration text", () => {
    renderSegmentCard({
      segment: makeSegment({
        novel_text: "Hero 拿起 Key。",
        characters_in_segment: ["Hero"],
        clues_in_segment: ["Key"],
      }),
      characters: { Hero: { description: "hero" } },
      clues: {
        Key: { description: "key", importance: "major" },
      },
    });

    const overlay = screen
      .getAllByTestId("mention-highlight-overlay")
      .find((node) => node.textContent === "Hero 拿起 Key。");

    expect(overlay).toBeDefined();
    expect(within(overlay!).getByText("Hero")).toHaveClass("text-cyan-300");
    expect(within(overlay!).getByText("Key")).toHaveClass("text-yellow-300");
  });

  it("shows live character mentions in the header before the segment is committed", () => {
    renderSegmentCard({
      segment: makeSegment({ characters_in_segment: [] }),
      characters: { "角色B": { description: "角色 B" } },
      onUpdatePrompt: vi.fn(),
    });

    const source = screen.getByLabelText("原文");
    fireEvent.change(source, { target: { value: "@角色B 進入畫面" } });

    expect(within(screen.getByTestId("avatar-stack")).getByText("角色B")).toBeInTheDocument();
  });

  it("removes live character mentions from the header when the draft becomes incomplete", () => {
    renderSegmentCard({
      segment: makeSegment({ characters_in_segment: [] }),
      characters: { "角色B": { description: "角色 B" } },
      onUpdatePrompt: vi.fn(),
    });

    const source = screen.getByLabelText("原文");
    fireEvent.change(source, { target: { value: "@角色B 進入畫面" } });
    fireEvent.change(source, { target: { value: "@角色" } });

    expect(within(screen.getByTestId("avatar-stack")).queryByText("角色B")).not.toBeInTheDocument();
  });

  it("uses @mentions in prompt text to update segment entities while keeping markers", () => {
    const onUpdatePrompt = vi.fn();
    renderSegmentCard({
      segment: makeSegment({ clues_in_segment: [] }),
      characters: { Hero: { description: "hero" } },
      clues: {
        Key: { description: "key", importance: "major" },
      },
      onUpdatePrompt,
    });

    const imagePrompt = screen.getByPlaceholderText("分鏡圖描述...");
    fireEvent.change(imagePrompt, { target: { value: "看到 @Hero 拿著 @Key" } });

    expect(onUpdatePrompt).toHaveBeenCalledWith(
      "SEG-1",
      "image_prompt",
      "看到 @Hero 拿著 @Key",
      {
        characters_in_segment: ["Hero"],
        clues_in_segment: ["Key"],
      },
    );
  });

  it("uses @scene mentions in prompt text to update the segment scene reference", () => {
    const onUpdatePrompt = vi.fn();
    renderSegmentCard({
      segment: makeSegment({
        characters_in_segment: [],
        clues_in_segment: [],
        scene_in_segment: null,
      }),
      scenes: { 古城: { description: "城牆與街道" } },
      onUpdatePrompt,
    });

    const imagePrompt = screen.getByPlaceholderText("分鏡圖描述...");
    fireEvent.change(imagePrompt, { target: { value: "遠景 @古城" } });

    expect(onUpdatePrompt).toHaveBeenCalledWith(
      "SEG-1",
      "image_prompt",
      "遠景 @古城",
      {
        scene_in_segment: "古城",
      },
    );
  });

  it("highlights known mentions inside drama dialogue lines", () => {
    renderSegmentCard({
      segment: makeDramaScene(),
      contentMode: "drama",
      characters: { Hero: { description: "hero" } },
      clues: {
        Key: { description: "key", importance: "major" },
      },
      scenes: { 古城: { description: "城牆與街道" } },
    });

    expect(screen.getByText("@古城")).toHaveClass("text-emerald-300");
    expect(screen.getByText("@Key")).toHaveClass("text-yellow-300");
  });

  it("disables unavailable duration choices when Veo constraints leave only 8 seconds", () => {
    const onUpdatePrompt = vi.fn();
    renderSegmentCard({
      segment: makeSegment({ duration_seconds: 8 }),
      durationOptions: [8],
      durationConstraintReason: "1080p/4k/參考圖強制 8 秒",
      onUpdatePrompt,
    });

    fireEvent.click(screen.getByRole("button", { name: /8s/i }));

    expect(screen.getByRole("radio", { name: "4s" })).toBeDisabled();
    expect(screen.getByRole("radio", { name: "6s" })).toBeDisabled();
    expect(screen.getByRole("radio", { name: "8s" })).not.toBeDisabled();
    expect(screen.getByRole("radio", { name: "4s" })).toHaveAttribute(
      "title",
      "1080p/4k/參考圖強制 8 秒",
    );
  });

  it("updates the per-scene video resolution when a resolution option is picked", () => {
    const onUpdatePrompt = vi.fn();
    renderSegmentCard({
      segment: makeSegment({ video_resolution: "720p" }),
      onUpdatePrompt,
    });

    // Open the resolution selector (current value shown on the trigger).
    fireEvent.click(screen.getByRole("button", { name: "影片解析度選擇" }));
    fireEvent.click(screen.getByRole("radio", { name: "1080p" }));

    expect(onUpdatePrompt).toHaveBeenCalledWith("SEG-1", "video_resolution", "1080p");
  });

  it("renders image size as a read-only chip when only one size is available", () => {
    // With provider lookups unmocked, image sizes fall back to the single
    // DEFAULT_IMAGE_SIZES entry, so the selector must not be interactive.
    renderSegmentCard({
      segment: makeSegment({ image_size: "1K" }),
      onUpdatePrompt: vi.fn(),
    });

    expect(
      screen.queryByRole("button", { name: "圖片解析度選擇" }),
    ).not.toBeInTheDocument();
  });

  it("auto-adjusts an invalid segment duration to the nearest allowed option", () => {
    const onUpdatePrompt = vi.fn();
    renderSegmentCard({
      segment: makeSegment({ duration_seconds: 4 }),
      durationOptions: [8],
      durationConstraintReason: "1080p 限制",
      onUpdatePrompt,
    });

    expect(onUpdatePrompt).toHaveBeenCalledWith("SEG-1", "duration_seconds", 8);
    expect(useAppStore.getState().toast?.text).toBe(
      "已自動將秒數從 4 調整為 8（1080p 限制）",
    );
  });

  it("prioritizes dynamicDurationOptions over project-level durationOptions", () => {
    vi.mocked(useVideoDurationOptions).mockReturnValue([12, 15]);

    const onUpdatePrompt = vi.fn();
    renderSegmentCard({
      segment: makeSegment({ duration_seconds: 12 }),
      durationOptions: [4, 6, 8],
      onUpdatePrompt,
    });

    fireEvent.click(screen.getByRole("button", { name: /12s/i }));

    expect(screen.getByRole("radio", { name: "12s" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "15s" })).toBeInTheDocument();
    expect(screen.queryByRole("radio", { name: "4s" })).not.toBeInTheDocument();
  });

  it("scopes storyboard controls to image model, image size, and image cost", () => {
    setSegmentCost();
    renderSegmentCard({
      stage: "storyboard",
      imageModelOptions: ["gemini-vertex/imagen-4"],
      videoModelOptions: ["gemini-aistudio/veo-3.1"],
      onUpdateSceneBackend: vi.fn(),
      onUpdatePrompt: vi.fn(),
    });

    expect(screen.getByRole("combobox", { name: "選擇分鏡圖圖片模型" })).toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "選擇分鏡影片模型" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /4s/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "影片解析度選擇" })).not.toBeInTheDocument();
    expect(screen.getByText("1K")).toBeInTheDocument();
    expect(screen.getByText("$0.12")).toBeInTheDocument();
    expect(screen.getByText("$0.02")).toBeInTheDocument();
    expect(screen.queryByText("$0.34")).not.toBeInTheDocument();
    expect(screen.queryByText("$0.03")).not.toBeInTheDocument();
  });

  it("renders the storyboard image model selector and the storyboard generate button", () => {
    renderSegmentCard({
      stage: "storyboard",
      imageModelOptions: ["gemini-vertex/imagen-4"],
      onUpdateSceneBackend: vi.fn(),
      onGenerateStoryboard: vi.fn(),
    });

    expect(screen.getByRole("combobox", { name: "選擇分鏡圖圖片模型" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "生圖" })).toBeInTheDocument();
  });

  it("labels storyboard prompt generation as prompt generation", () => {
    renderSegmentCard({
      stage: "storyboard",
      textModelOptions: ["gemini/gemini-2.5-flash"],
      onUpdatePrompt: vi.fn(),
    });

    expect(screen.getByRole("button", { name: "生成提示詞" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "AI 生成" })).not.toBeInTheDocument();
  });

  it("uses drama scene description and dialogue lines as prompt generation context", async () => {
    const generateSpy = vi
      .spyOn(API, "generateAIDescription")
      .mockResolvedValue({ success: true, prompt: "新的分鏡提示詞" });

    renderSegmentCard({
      segment: makeDramaScene({
        scene_description: "Hero 在古城門前發現 Key 正在泛光。",
        video_prompt: {
          action: "Hero 走向 Key",
          camera_motion: "Static",
          ambiance_audio: "夜風吹過城門",
          dialogue: [{ speaker: "Hero", line: "這把 Key 在發光。" }],
        },
      }),
      contentMode: "drama",
      stage: "storyboard",
      textModelOptions: ["gemini/gemini-2.5-flash"],
      onUpdatePrompt: vi.fn(),
    });

    fireEvent.click(screen.getByRole("button", { name: "生成提示詞" }));

    await waitFor(() => expect(generateSpy).toHaveBeenCalledTimes(1));
    const payload = generateSpy.mock.calls[0][1];
    expect(payload.description).toContain("場景描述:\nHero 在古城門前發現 Key 正在泛光。");
    expect(payload.description).toContain("對話:\nHero: 這把 Key 在發光。");
  });

  it("uses the edited source draft when generating a storyboard prompt", async () => {
    const generateSpy = vi
      .spyOn(API, "generateAIDescription")
      .mockResolvedValue({ success: true, prompt: "新的分鏡提示詞" });

    renderSegmentCard({
      segment: makeDramaScene({
        scene_description: "舊的時間軸描述。",
      }),
      contentMode: "drama",
      stage: "storyboard",
      textModelOptions: ["gemini/gemini-2.5-flash"],
      onUpdatePrompt: vi.fn(),
    });

    fireEvent.change(screen.getByLabelText("原文"), {
      target: { value: "剛編輯尚未儲存的時間軸描述。" },
    });
    fireEvent.click(screen.getByRole("button", { name: "生成提示詞" }));

    await waitFor(() => expect(generateSpy).toHaveBeenCalledTimes(1));
    const payload = generateSpy.mock.calls[0][1];
    expect(payload.description).toContain("剛編輯尚未儲存的時間軸描述。");
    expect(payload.description).not.toContain("舊的時間軸描述。");
  });

  it("includes style and reference image context when generating a storyboard prompt", async () => {
    const generateSpy = vi
      .spyOn(API, "generateAIDescription")
      .mockResolvedValue({ success: true, prompt: "新的分鏡提示詞" });

    renderSegmentCard({
      segment: makeSegment({
        reference_image: "refs/SEG-1-reference.png",
      }),
      stage: "storyboard",
      textModelOptions: ["gemini/gemini-2.5-flash"],
      styleContext: {
        style: "水墨動畫",
        styleDescription: "留白、淡墨、柔和紙張紋理",
        styleImage: "style/style-reference.png",
      },
      onUpdatePrompt: vi.fn(),
    });

    fireEvent.click(screen.getByRole("button", { name: "生成提示詞" }));

    await waitFor(() => expect(generateSpy).toHaveBeenCalledTimes(1));
    const payload = generateSpy.mock.calls[0][1];
    expect(payload.description).toContain("專案風格: 水墨動畫");
    expect(payload.description).toContain("風格描述:\n留白、淡墨、柔和紙張紋理");
    expect(payload.description).toContain("風格參考圖: style/style-reference.png");
    expect(payload.description).toContain("分鏡參考圖: refs/SEG-1-reference.png");
  });

  it("does not auto-adjust video duration while editing storyboard image controls", () => {
    const onUpdatePrompt = vi.fn();
    renderSegmentCard({
      stage: "storyboard",
      segment: makeSegment({ duration_seconds: 4 }),
      durationOptions: [8],
      durationConstraintReason: "1080p 限制",
      onUpdatePrompt,
    });

    expect(onUpdatePrompt).not.toHaveBeenCalledWith("SEG-1", "duration_seconds", 8);
  });

  it("scopes video controls to video model, video resolution, duration, and video cost", () => {
    setSegmentCost();
    renderSegmentCard({
      stage: "video",
      imageModelOptions: ["gemini-vertex/imagen-4"],
      videoModelOptions: ["gemini-aistudio/veo-3.1"],
      onUpdateSceneBackend: vi.fn(),
      onUpdatePrompt: vi.fn(),
    });

    expect(screen.getByRole("combobox", { name: "選擇分鏡影片模型" })).toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "選擇分鏡圖圖片模型" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /4s/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "影片解析度選擇" })).toBeInTheDocument();
    expect(screen.queryByText("1K")).not.toBeInTheDocument();
    expect(screen.getByText("$0.34")).toBeInTheDocument();
    expect(screen.getByText("$0.03")).toBeInTheDocument();
    expect(screen.queryByText("$0.12")).not.toBeInTheDocument();
    expect(screen.queryByText("$0.02")).not.toBeInTheDocument();
  });

  it("labels video prompt generation as prompt generation", () => {
    renderSegmentCard({
      stage: "video",
      textModelOptions: ["gemini/gemini-2.5-flash"],
      onUpdatePrompt: vi.fn(),
    });

    expect(screen.getByRole("button", { name: "生成提示詞" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "AI 生成" })).not.toBeInTheDocument();
  });

  it("keeps storyboard and video media frames capped when the workspace expands", () => {
    renderSegmentCard();

    expect(screen.getByTestId("storyboard-media-frame")).toHaveClass("max-w-[18rem]");
    expect(screen.getByTestId("video-media-frame")).toHaveClass("max-w-[18rem]");
  });
});
