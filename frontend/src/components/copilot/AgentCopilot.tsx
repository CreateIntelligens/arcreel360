import { useState, useRef, useCallback } from "react";
import { useLocation } from "wouter";
import { Bot, Send, Square, Paperclip, X } from "lucide-react";
import { ImageLightbox } from "@/components/ui/ImageLightbox";
import { useAssistantStore } from "@/stores/assistant-store";
import { useProjectsStore } from "@/stores/projects-store";
import { useAppStore } from "@/stores/app-store";
import { useAssistantSession } from "@/hooks/useAssistantSession";
import { useAssistantProviderId } from "@/hooks/useAssistantProviderId";
import { useAutoScrollOnChange } from "@/hooks/useAutoScrollOnChange";
import { useRefocusAfterSend } from "@/hooks/useRefocusAfterSend";
import {
  ASSISTANT_PROVIDER_LABELS,
  inferAssistantProvider,
  resolveAssistantCapabilities,
} from "@/types";
import { ContextBanner } from "./ContextBanner";
import { PendingQuestionWizard } from "./PendingQuestionWizard";
import { SlashCommandMenu } from "./SlashCommandMenu";
import type { SlashCommandMenuHandle } from "./SlashCommandMenu";
import { TodoListPanel } from "./TodoListPanel";
import { ChatMessage } from "./chat/ChatMessage";
import { CopilotHeader } from "./agent-copilot/CopilotHeader";
import { useImageAttachments } from "./agent-copilot/useImageAttachments";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const MAX_TEXTAREA_HEIGHT_VH = 50;

// ---------------------------------------------------------------------------
// AgentCopilot — 主面板
// ---------------------------------------------------------------------------

export function AgentCopilot() {
  const {
    turns, draftTurn, messagesLoading,
    sending, sessionStatus, pendingQuestion, answeringQuestion, error,
    sessions, currentSessionId,
  } = useAssistantStore();

  const { currentProjectName } = useProjectsStore();
  const toggleAssistantPanel = useAppStore((s) => s.toggleAssistantPanel);
  const [, setLocation] = useLocation();
  const { sendMessage, answerQuestion, interrupt, createNewSession, switchSession, deleteSession } =
    useAssistantSession(currentProjectName);

  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const slashMenuRef = useRef<SlashCommandMenuHandle>(null);
  const [localInput, setLocalInput] = useState("");
  const [showSlashMenu, setShowSlashMenu] = useState(false);
  const [lightboxSrc, setLightboxSrc] = useState<string | null>(null);
  const {
    attachedImages,
    attachError,
    isDragOver,
    maxImages,
    invalidatePending,
    setAttachedImages,
    setAttachError,
    removeImage,
    handlePaste,
    handleDragOver,
    handleDragLeave,
    handleDrop,
    handleFileSelect,
  } = useImageAttachments();
  const activeProviderId = useAssistantProviderId();
  const allTurns = draftTurn ? [...turns, draftTurn] : turns;
  const currentSession = sessions.find((session) => session.id === currentSessionId) ?? null;
  const providerCapabilities = resolveAssistantCapabilities(
    currentSession,
    activeProviderId || inferAssistantProvider(currentSessionId),
  );
  const providerLabel = ASSISTANT_PROVIDER_LABELS[providerCapabilities.provider] ?? providerCapabilities.provider;
  const isRunning = sessionStatus === "running";
  const slashCommandsEnabled = providerCapabilities.supports_tool_calls || providerCapabilities.supports_subagents;
  const inputDisabled = Boolean(pendingQuestion) || answeringQuestion || isRunning || sending;
  const attachDisabled = inputDisabled || !providerCapabilities.supports_images || attachedImages.length >= maxImages;
  const requestRefocusAfterSend = useRefocusAfterSend(inputDisabled, textareaRef);
  // 串流中同一則 turn 的內容會持續變長，僅靠 turn 數無法觸發捲動，
  // 故把最後一則 turn 的 block 數與末塊文字長度納入 signal。
  const lastTurn = allTurns[allTurns.length - 1];
  const lastBlock = lastTurn?.content[lastTurn.content.length - 1];
  const streamingSignal = `${allTurns.length}:${lastTurn?.content.length ?? 0}:${
    (lastBlock?.text ?? lastBlock?.thinking ?? lastBlock?.result ?? lastBlock?.skill_content ?? "").length
  }`;
  useAutoScrollOnChange(scrollRef, streamingSignal);

  const inputPlaceholder = pendingQuestion
    ? "請先回答上方問題"
    : isRunning
      ? "助理正在生成中，可點選停止中斷"
      : slashCommandsEnabled
        ? "輸入訊息，輸入 / 檢視可用技能"
        : "輸入訊息開始對話";

  const handleSend = useCallback(() => {
    if (inputDisabled || (!localInput.trim() && attachedImages.length === 0)) return;
    requestRefocusAfterSend();
    invalidatePending(); // invalidate pending FileReader callbacks
    sendMessage(localInput.trim(), attachedImages.length > 0 ? attachedImages : undefined);
    setLocalInput("");
    setAttachedImages([]);
    setAttachError(null);
    setShowSlashMenu(false);
    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }, [
    inputDisabled,
    localInput,
    attachedImages,
    sendMessage,
    requestRefocusAfterSend,
    invalidatePending,
    setAttachedImages,
    setAttachError,
  ]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    // Delegate to slash menu when open
    if (showSlashMenu && slashMenuRef.current) {
      const consumed = slashMenuRef.current.handleKeyDown(e.key);
      if (consumed) {
        e.preventDefault();
        if (e.key === "Escape") setShowSlashMenu(false);
        return;
      }
    }
    if (e.nativeEvent.isComposing) {
      return;
    }
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }, [handleSend, showSlashMenu]);

  // Track the slash "/" position so we know where the command token starts
  const slashPosRef = useRef(-1);

  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target.value;
    const cursor = e.target.selectionStart ?? val.length;
    setLocalInput(val);

    // Check text left of cursor: trigger menu when "/" is at start or after whitespace/newline
    const textBeforeCursor = val.slice(0, cursor);
    const lastSlash = textBeforeCursor.lastIndexOf("/");
    if (lastSlash >= 0) {
      const charBefore = lastSlash > 0 ? textBeforeCursor[lastSlash - 1] : undefined;
      const atBoundary = charBefore === undefined || /\s/.test(charBefore);
      const afterSlash = textBeforeCursor.slice(lastSlash + 1);
      const noSpaceAfterSlash = !afterSlash.includes(" ");
      if (slashCommandsEnabled && atBoundary && noSpaceAfterSlash) {
        setShowSlashMenu(true);
        slashPosRef.current = lastSlash;
      } else {
        setShowSlashMenu(false);
        slashPosRef.current = -1;
      }
    } else {
      setShowSlashMenu(false);
      slashPosRef.current = -1;
    }

    // Auto-resize: grow upward until 50vh, then scroll
    const el = e.target;
    el.style.height = "auto";
    const maxH = window.innerHeight * (MAX_TEXTAREA_HEIGHT_VH / 100);
    el.style.height = `${Math.min(el.scrollHeight, maxH)}px`;
    el.style.overflowY = el.scrollHeight > maxH ? "auto" : "hidden";
  }, [slashCommandsEnabled]);

  // Derive slash filter from input (text after "/" up to cursor)
  const slashFilter = showSlashMenu && slashPosRef.current >= 0
    ? localInput.slice(slashPosRef.current + 1).split(/\s/)[0]
    : "";

  const handleSlashSelect = useCallback((cmd: string) => {
    // Replace the "/filter" token with the selected command, keep surrounding text
    const pos = slashPosRef.current;
    if (pos >= 0) {
      const before = localInput.slice(0, pos);
      // Find end of the slash token (next whitespace or end of string)
      const afterSlash = localInput.slice(pos);
      const tokenEnd = afterSlash.search(/\s/);
      const after = tokenEnd >= 0 ? localInput.slice(pos + tokenEnd) : "";
      setLocalInput(before + cmd + " " + after.trimStart());
    } else {
      setLocalInput(localInput + cmd + " ");
    }
    setShowSlashMenu(false);
    slashPosRef.current = -1;
    textareaRef.current?.focus();
  }, [localInput]);

  return (
    <div className="relative isolate flex h-full flex-col">
      <CopilotHeader
        providerLabel={providerLabel}
        isRunning={isRunning}
        onTogglePanel={toggleAssistantPanel}
        onCreateNewSession={createNewSession}
        onSwitchSession={switchSession}
        onDeleteSession={deleteSession}
      />

      {/* Context banner */}
      <ContextBanner />

      {providerCapabilities.tier === "lite" && (
        <div className="flex items-start gap-2 border-b border-sky-900/30 bg-sky-950/20 px-3 py-2 text-xs text-sky-200">
          <span className="flex-1">
            目前為「對話模式」，僅支援文字交流。如需 AI 自動化生成劇本／分鏡／角色，請切換為「工作流模式」。
          </span>
          <button
            type="button"
            onClick={() => setLocation("/app/settings")}
            className="shrink-0 rounded-md border border-sky-700/40 bg-sky-900/30 px-2 py-0.5 text-[11px] font-medium text-sky-100 transition-colors hover:bg-sky-800/40"
          >
            前往設定
          </button>
        </div>
      )}

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 min-w-0 overflow-y-auto overflow-x-hidden px-3 py-3 space-y-3">
        {allTurns.length === 0 && !messagesLoading && (
          <div className="flex h-full flex-col items-center justify-center text-center text-gray-500">
            <Bot className="mb-3 h-8 w-8 text-gray-600" />
            <p className="text-sm">在下方輸入訊息開始對話</p>
            {slashCommandsEnabled ? (
              <p className="mt-1 text-xs text-gray-600">輸入 / 可快速呼叫技能</p>
            ) : (
              <p className="mt-1 text-xs text-gray-600">目前 provider 僅提供基礎對話能力</p>
            )}
          </div>
        )}
        {allTurns.map((turn, i) => (
          <ChatMessage key={turn.uuid || `turn-${i}`} message={turn} />
        ))}
      </div>

      {pendingQuestion && (
        <PendingQuestionWizard
          pendingQuestion={pendingQuestion}
          answeringQuestion={answeringQuestion}
          error={error}
          onSubmitAnswers={answerQuestion}
        />
      )}

      <TodoListPanel turns={turns} draftTurn={draftTurn} />

      {!pendingQuestion && (error || attachError) && (
        <div className="border-t border-red-400/20 bg-red-500/10 px-3 py-2 text-xs text-red-300">
          {error || attachError}
        </div>
      )}

      {/* Input area */}
      <div className="border-t border-gray-800 p-3">
        {/* Thumbnail strip */}
        {attachedImages.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-2">
            {attachedImages.map((img) => (
              <div key={img.id} className="relative">
                <button
                  type="button"
                  className="h-16 w-16 cursor-pointer border-0 bg-transparent p-0"
                  onClick={() => setLightboxSrc(img.dataUrl)}
                  aria-label="點選放大圖片"
                >
                  <img
                    src={img.dataUrl}
                    alt="附件預覽"
                    className="h-16 w-16 rounded-md object-cover border border-gray-600"
                  />
                </button>
                <button
                  type="button"
                  onClick={() => removeImage(img.id)}
                  className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full bg-gray-900 text-gray-300 hover:bg-red-500 hover:text-white"
                  aria-label="移除圖片"
                >
                  <X className="h-2.5 w-2.5" />
                </button>
              </div>
            ))}
          </div>
        )}

        <div
          className={`relative flex items-end gap-2 rounded-lg border bg-gray-800 px-3 py-2 transition-colors ${
            isDragOver ? "border-indigo-500 bg-indigo-500/10" : "border-gray-700"
          }`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          {showSlashMenu && (
            <SlashCommandMenu
              ref={slashMenuRef}
              filter={slashFilter}
              onSelect={handleSlashSelect}
            />
          )}
          <textarea
            ref={textareaRef}
            role="combobox"
            value={localInput}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            onPaste={handlePaste}
            placeholder={inputPlaceholder}
            rows={1}
            aria-label="助理輸入"
            aria-expanded={showSlashMenu}
            aria-controls={showSlashMenu ? "slash-command-menu" : undefined}
            aria-activedescendant={slashMenuRef.current?.activeDescendantId}
            className="flex-1 resize-none bg-transparent text-sm text-gray-200 placeholder-gray-500 outline-none overflow-hidden"
            style={{ maxHeight: `${MAX_TEXTAREA_HEIGHT_VH}vh` }}
            disabled={inputDisabled}
          />

          {/* Attachment button */}
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={attachDisabled}
            className="shrink-0 rounded p-1.5 text-gray-400 hover:bg-gray-700 hover:text-gray-200 disabled:opacity-30"
            title={
              !providerCapabilities.supports_images
                ? "目前 provider 不支援圖片輸入"
                : attachedImages.length >= maxImages
                  ? `最多附加 ${maxImages} 張圖片`
                  : "附加圖片"
            }
            aria-label="附加圖片"
          >
            <Paperclip className="h-4 w-4" />
          </button>

          {isRunning ? (
            <button
              onClick={interrupt}
              className="shrink-0 rounded p-1.5 text-red-400 hover:bg-gray-700"
              title="中斷會話"
              aria-label="中斷會話"
            >
              <Square className="h-4 w-4" />
            </button>
          ) : (
            <button
              onClick={handleSend}
              disabled={(!localInput.trim() && attachedImages.length === 0) || inputDisabled}
              className="shrink-0 rounded p-1.5 text-indigo-400 hover:bg-gray-700 disabled:opacity-30"
              title="傳送訊息"
              aria-label="傳送訊息"
            >
              <Send className="h-4 w-4" />
            </button>
          )}
        </div>

        {/* Hidden file input */}
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept="image/*"
          className="hidden"
          onChange={handleFileSelect}
        />
      </div>

      {lightboxSrc && (
        <ImageLightbox
          src={lightboxSrc}
          alt="附件預覽"
          onClose={() => setLightboxSrc(null)}
        />
      )}
    </div>
  );
}
