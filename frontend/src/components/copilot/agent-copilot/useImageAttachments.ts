import { useCallback, useRef, useState } from "react";
import type { AttachedImage } from "@/hooks/useAssistantSession";
import { uid } from "@/utils/id";

const MAX_IMAGES = 5;
const MAX_IMAGE_BYTES = 5 * 1024 * 1024; // 5MB

export interface UseImageAttachmentsResult {
  attachedImages: AttachedImage[];
  attachError: string | null;
  isDragOver: boolean;
  maxImages: number;
  /** 由 send 完成時呼叫，使尚未讀完的 FileReader 失效 */
  invalidatePending: () => void;
  setAttachedImages: React.Dispatch<React.SetStateAction<AttachedImage[]>>;
  setAttachError: (msg: string | null) => void;
  addImages: (files: File[]) => void;
  removeImage: (id: string) => void;
  handlePaste: (e: React.ClipboardEvent) => void;
  handleDragOver: (e: React.DragEvent) => void;
  handleDragLeave: () => void;
  handleDrop: (e: React.DragEvent) => void;
  handleFileSelect: (e: React.ChangeEvent<HTMLInputElement>) => void;
}

export function useImageAttachments(): UseImageAttachmentsResult {
  const [attachedImages, setAttachedImages] = useState<AttachedImage[]>([]);
  const [attachError, setAttachError] = useState<string | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const imageGenRef = useRef(0);

  const invalidatePending = useCallback(() => {
    imageGenRef.current += 1;
  }, []);

  const addImages = useCallback((files: File[]) => {
    setAttachError(null);
    const gen = imageGenRef.current;
    for (const file of files) {
      if (!file.type.startsWith("image/")) continue;
      if (file.size > MAX_IMAGE_BYTES) {
        setAttachError(`圖片「${file.name}」超過 5MB，已跳過`);
        continue;
      }
      const reader = new FileReader();
      reader.onload = (e) => {
        if (imageGenRef.current !== gen) return; // stale — message already sent
        const dataUrl = e.target?.result as string;
        setAttachedImages((prev) => {
          if (prev.length >= MAX_IMAGES) return prev;
          return [...prev, { id: uid(), dataUrl, mimeType: file.type }];
        });
      };
      reader.readAsDataURL(file);
    }
  }, []);

  const removeImage = useCallback((id: string) => {
    setAttachedImages((prev) => prev.filter((img) => img.id !== id));
    setAttachError(null);
  }, []);

  const handlePaste = useCallback((e: React.ClipboardEvent) => {
    const items = Array.from(e.clipboardData.items);
    const imageItems = items.filter((item) => item.type.startsWith("image/"));
    if (imageItems.length === 0) return;
    e.preventDefault();
    const files = imageItems.map((item) => item.getAsFile()).filter(Boolean) as File[];
    addImages(files);
  }, [addImages]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    const hasFiles = Array.from(e.dataTransfer.items).some((i) => i.kind === "file");
    if (!hasFiles) return;
    e.preventDefault();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback(() => {
    setIsDragOver(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    const files = Array.from(e.dataTransfer.files).filter((f) => f.type.startsWith("image/"));
    if (files.length > 0) addImages(files);
  }, [addImages]);

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    if (files.length > 0) addImages(files);
    e.target.value = "";
  }, [addImages]);

  return {
    attachedImages,
    attachError,
    isDragOver,
    maxImages: MAX_IMAGES,
    invalidatePending,
    setAttachedImages,
    setAttachError,
    addImages,
    removeImage,
    handlePaste,
    handleDragOver,
    handleDragLeave,
    handleDrop,
    handleFileSelect,
  };
}
