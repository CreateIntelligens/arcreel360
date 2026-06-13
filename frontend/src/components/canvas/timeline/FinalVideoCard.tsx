import { useEffect, useState, useCallback } from "react";
import { API } from "@/api";
import { useAppStore } from "@/stores/app-store";
import { PreviewableVideoFrame } from "@/components/ui/PreviewableVideoFrame";
import { VersionTimeMachine } from "./VersionTimeMachine";

interface FinalVideoCardProps {
  projectName: string;
  episode: number;
}

interface OutputFile {
  name: string;
  size: number;
  url: string;
}

function isFinalVideoFile(file: OutputFile): boolean {
  return /_final(?:_with_music)?\.(mp4|webm)$/i.test(file.name);
}

function pickFinalVideoFile(files: OutputFile[], episode: number): OutputFile | null {
  // 確定性命名：episode_N_final.mp4（也容許 .webm 與 _with_music 變體）。
  const episodePrefix = `episode_${episode}_final`;
  const episodeNamed = files.find((f) => f.name.startsWith(episodePrefix) && /\.(mp4|webm)$/i.test(f.name));
  if (episodeNamed) return episodeNamed;

  // 舊檔以標題命名（無集數），僅當唯一時才回退採用。
  const legacyFinals = files.filter(isFinalVideoFile);
  return legacyFinals.length === 1 ? legacyFinals[0] : null;
}

export function FinalVideoCard({ projectName, episode }: FinalVideoCardProps) {
  const [file, setFile] = useState<OutputFile | null>(null);
  const [loading, setLoading] = useState(true);

  const targetName = `episode_${episode}_final.mp4`;
  // 合成成功後 EpisodeActionsBar 會 invalidate 此 key，觸發自動重抓。
  const composeRevision = useAppStore((s) => s.getEntityRevision(`final:episode_${episode}`));

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const res = await API.listFiles(projectName);
      setFile(pickFinalVideoFile(res.files?.output ?? [], episode));
    } catch {
      setFile(null);
    } finally {
      setLoading(false);
    }
  }, [episode, projectName]);

  const handleRestoreVersion = useCallback(() => {
    useAppStore.getState().invalidateEntities([`final:episode_${episode}`]);
  }, [episode]);

  useEffect(() => {
    void refresh();
  }, [refresh, composeRevision]);

  const fileUrl = file ? API.getFileUrl(projectName, `output/${file.name}`) : null;

  return (
    <div className="mt-6 rounded-xl border border-gray-800 bg-gray-950/40 p-4">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <div className="text-sm font-medium text-gray-100">最終成片</div>
          <div className="text-xs text-gray-500">{file?.name ?? targetName}</div>
        </div>
        <div className="flex items-center gap-2">
          {file?.name === targetName && (
            <VersionTimeMachine
              projectName={projectName}
              resourceType="output"
              resourceId={String(episode)}
              onRestore={handleRestoreVersion}
            />
          )}
          <button
            type="button"
            onClick={() => void refresh()}
            className="text-xs text-gray-400 hover:text-gray-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500/60 rounded px-2 py-1"
          >
            重新整理
          </button>
        </div>
      </div>

      {loading ? (
        <div className="text-xs text-gray-500">載入中…</div>
      ) : file && fileUrl ? (
        <div className="space-y-2">
          <PreviewableVideoFrame src={fileUrl} alt="最終成片">
            <video
              key={file.url}
              controls
              preload="metadata"
              className="w-full rounded-lg bg-black"
              src={fileUrl}
            />
          </PreviewableVideoFrame>
          <div className="flex items-center justify-between text-xs text-gray-500">
            <span>{(file.size / 1024 / 1024).toFixed(1)} MB</span>
            <a
              href={fileUrl}
              download={file.name}
              className="text-indigo-400 hover:text-indigo-300"
            >
              下載
            </a>
          </div>
        </div>
      ) : (
        <div className="rounded-lg border border-gray-800 bg-gray-900/40 px-3 py-4 text-xs text-gray-500">
          尚未產生成片。請先在「影片時間線」生成各場景影片，再點上方「合成成片」按鈕拼接最終成片。
        </div>
      )}
    </div>
  );
}
