import { useEffect, useRef, useState } from "react";
import { X, Loader2, ImagePlus, Upload } from "lucide-react";

interface AddSceneFormProps {
  onSubmit: (
    name: string,
    description: string,
    referenceFile?: File | null,
  ) => Promise<void>;
  onCancel: () => void;
}

export function AddSceneForm({ onSubmit, onCancel }: AddSceneFormProps) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [referenceFile, setReferenceFile] = useState<File | null>(null);
  const [referencePreview, setReferencePreview] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    return () => {
      if (referencePreview) {
        URL.revokeObjectURL(referencePreview);
      }
    };
  }, [referencePreview]);

  const handleReferenceChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (referencePreview) {
      URL.revokeObjectURL(referencePreview);
    }

    setReferenceFile(file);
    setReferencePreview(URL.createObjectURL(file));
    e.target.value = "";
  };

  const clearReference = () => {
    if (referencePreview) {
      URL.revokeObjectURL(referencePreview);
    }
    setReferenceFile(null);
    setReferencePreview(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setSubmitting(true);
    try {
      await onSubmit(name.trim(), description.trim(), referenceFile);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="rounded-xl border border-indigo-500/30 bg-gray-900 p-5"
      data-workspace-editing="true"
    >
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-200">新增場景</h3>
        <button
          type="button"
          onClick={onCancel}
          className="rounded p-1 text-gray-400 hover:bg-gray-800 hover:text-gray-200"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <label className="mb-1 block text-xs font-medium text-gray-400">
            名稱 <span className="text-red-400">*</span>
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="場景名稱"
            className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-1.5 text-sm text-gray-200 placeholder-gray-500 outline-none focus:border-indigo-500"
            autoFocus
          />
        </div>

        <div>
          <label className="mb-1 block text-xs font-medium text-gray-400">
            描述 <span className="text-gray-600">（選填）</span>
          </label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="場景的環境、氛圍、視覺特徵等描述..."
            rows={3}
            className="w-full resize-none rounded-lg border border-gray-700 bg-gray-800 px-3 py-1.5 text-sm text-gray-200 placeholder-gray-500 outline-none focus:border-indigo-500"
          />
        </div>

        <div>
          <div className="mb-1 flex items-center justify-between">
            <label className="block text-xs font-medium text-gray-400">
              參考圖 <span className="text-gray-600">（可選）</span>
            </label>
            {referenceFile && (
              <span className="text-[11px] text-gray-500">{referenceFile.name}</span>
            )}
          </div>

          {referencePreview ? (
            <div className="relative overflow-hidden rounded-lg border border-gray-700 bg-gray-800 h-32">
              <img
                src={referencePreview}
                alt="場景參考圖預覽"
                className="h-full w-full object-cover"
              />
              <div className="absolute inset-x-0 bottom-0 flex items-center justify-between bg-gradient-to-t from-black/70 to-transparent px-3 py-2">
                <span className="flex items-center gap-1.5 text-xs text-gray-200">
                  <ImagePlus className="h-3.5 w-3.5" />
                  已選擇參考圖
                </span>
                <div className="flex items-center gap-1.5">
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    className="rounded bg-black/40 px-2 py-1 text-xs text-gray-200 transition-colors hover:bg-black/60"
                  >
                    更換
                  </button>
                  <button
                    type="button"
                    onClick={clearReference}
                    className="rounded bg-black/40 px-2 py-1 text-xs text-gray-200 transition-colors hover:bg-black/60"
                  >
                    清除
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="flex h-32 w-full flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-gray-700 bg-gray-800/50 text-sm text-gray-500 transition-colors hover:border-gray-500 hover:text-gray-300"
            >
              <Upload className="h-6 w-6" />
              <span>上傳參考圖片</span>
            </button>
          )}

          <input
            ref={fileInputRef}
            type="file"
            accept=".png,.jpg,.jpeg,.webp"
            onChange={handleReferenceChange}
            className="hidden"
          />
          <p className="mt-1 text-xs text-gray-600">
            用於後續場景生成時保持環境風格一致性
          </p>
        </div>

        <div className="flex justify-end gap-2 pt-1">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-lg px-3 py-1.5 text-sm text-gray-400 transition-colors hover:text-gray-200"
          >
            取消
          </button>
          <button
            type="submit"
            disabled={submitting || !name.trim()}
            className="rounded-lg bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {submitting ? (
              <span className="inline-flex items-center gap-1.5">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                新增中...
              </span>
            ) : (
              "新增"
            )}
          </button>
        </div>
      </form>
    </div>
  );
}
