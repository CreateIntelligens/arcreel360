from __future__ import annotations

import json
import logging
import re
import shutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib.project_manager import ProjectManager

logger = logging.getLogger(__name__)

EPISODE_FILENAME_PATTERN = re.compile(r"episode[_\s]*(\d+)", re.IGNORECASE)


def _episode_from_filename(filename: str) -> int | None:
    """從劇本檔名解析集數，如 episode_2.json → 2；無法解析時回傳 None。"""
    match = EPISODE_FILENAME_PATTERN.search(filename)
    return int(match.group(1)) if match else None


def _next_display_order(episodes: list[dict]) -> int:
    """回傳下一個顯示順序值（max(現有 order) + 1，無資料時為 0）。"""
    max_order = -1
    for ep in episodes:
        value = ep.get("order")
        if isinstance(value, int) and value > max_order:
            max_order = value
    return max_order + 1


class EpisodeManager:
    """劇集管理器（處理分集切分與跨目錄物理劇集清理）"""

    def __init__(self, project_manager: ProjectManager):
        self.pm = project_manager

    def remove_episode(self, project_name: str, episode: int) -> tuple[dict, list[str]]:
        """從專案移除一整集。

        會刪除：劇本檔（scripts/episode_N.json）、預處理草稿（drafts/episode_N/）、
        分集切分產生的 source/episode_N.txt、合成輸出（output/episode_N*.{mp4,webm}）、
        該集所有片段/場景對應的分鏡/影片/縮圖與版本檔（versions/）及 versions.json 內的條目，
        最後從 project.json 的 episodes 移除該條目。
        """
        project = self.pm.load_project(project_name)
        episodes = project.get("episodes", [])
        entry = next((ep for ep in episodes if int(ep.get("episode", -1)) == int(episode)), None)
        if entry is None:
            raise KeyError(f"劇集 E{episode} 不存在")

        project_dir = self.pm.get_project_path(project_name)
        removed: list[str] = []
        ep_prefix = f"E{int(episode)}S"

        def _rm_file(rel: str) -> None:
            p = project_dir / rel
            if p.is_file():
                p.unlink()
                removed.append(rel)

        def _rm_dir(rel: str) -> None:
            p = project_dir / rel
            if p.is_dir():
                shutil.rmtree(p)
                removed.append(rel.rstrip("/") + "/")

        # 收集該集所有片段/場景 id（劇本可能損毀或不存在 → 退回前綴掃描）
        script_rel = entry.get("script_file") or f"scripts/episode_{episode}.json"
        script_name = script_rel[len("scripts/") :] if script_rel.startswith("scripts/") else script_rel
        segment_ids: set[str] = set()
        try:
            script = self.pm.load_script(project_name, script_name)
            for key in ("segments", "scenes"):
                for item in script.get(key, []) or []:
                    sid = item.get("segment_id") or item.get("scene_id")
                    if isinstance(sid, str) and sid:
                        segment_ids.add(sid)
        except (FileNotFoundError, json.JSONDecodeError, ValueError, AttributeError):
            pass

        def _id_hit(resource_id: str) -> bool:
            return resource_id in segment_ids if segment_ids else resource_id.startswith(ep_prefix)

        # 1) 劇本檔
        _rm_file(f"scripts/{script_name}")
        # 2) 預處理草稿目錄
        _rm_dir(f"drafts/episode_{episode}")
        # 3) 分集切分產生的 source/episode_N.txt
        _rm_file(f"source/episode_{episode}.txt")
        # 4) 合成輸出 output/episode_N*.{mp4,webm}
        output_dir = project_dir / "output"
        if output_dir.is_dir():
            for f in sorted(output_dir.iterdir()):
                if f.is_file() and f.name.startswith(f"episode_{episode}") and f.suffix.lower() in (".mp4", ".webm"):
                    f.unlink()
                    removed.append(f"output/{f.name}")
        # 5) 各片段/場景的分鏡、影片、縮圖（檔名格式：scene_{id}.{ext}）
        media_dirs = {
            "storyboards": (".png", ".jpg", ".jpeg"),
            "videos": (".mp4", ".webm"),
            "thumbnails": (".png", ".jpg", ".jpeg"),
        }
        for sub, exts in media_dirs.items():
            d = project_dir / sub
            if not d.is_dir():
                continue
            for f in sorted(d.iterdir()):
                if not f.is_file() or f.suffix.lower() not in exts:
                    continue
                stem = f.stem
                resource_id = stem[len("scene_") :] if stem.startswith("scene_") else stem
                if _id_hit(resource_id):
                    f.unlink()
                    removed.append(f"{sub}/{f.name}")
        # 6) versions/ 目錄檔案與 versions.json 條目（檔名格式：{id}_v{n}_{timestamp}.{ext}）
        versions_dir = project_dir / "versions"
        if versions_dir.is_dir():
            for rt in ("storyboards", "videos"):
                rt_dir = versions_dir / rt
                if not rt_dir.is_dir():
                    continue
                for f in sorted(rt_dir.iterdir()):
                    if not f.is_file():
                        continue
                    resource_id = f.name.split("_v", 1)[0]
                    if _id_hit(resource_id):
                        f.unlink()
                        removed.append(f"versions/{rt}/{f.name}")
            versions_file = versions_dir / "versions.json"
            if versions_file.is_file():
                try:
                    with open(versions_file, encoding="utf-8") as fh:  # noqa: PTH123
                        vdata = json.load(fh)
                    changed = False
                    for rt in ("storyboards", "videos"):
                        bucket = vdata.get(rt)
                        if not isinstance(bucket, dict):
                            continue
                        for resource_id in list(bucket.keys()):
                            if _id_hit(resource_id):
                                del bucket[resource_id]
                                changed = True
                    if changed:
                        with open(versions_file, "w", encoding="utf-8") as fh:  # noqa: PTH123
                            json.dump(vdata, fh, ensure_ascii=False, indent=2)
                        removed.append("versions/versions.json")
                except (json.JSONDecodeError, OSError):
                    pass

        # 7) 從 project.json 移除該集
        project["episodes"] = [ep for ep in episodes if int(ep.get("episode", -1)) != int(episode)]
        self.pm.save_project(project_name, project)
        return project, removed

    def commit_episode_split(
        self,
        project_name: str,
        source_rel: str,
        episode: int,
        part_before: str,
        part_after: str,
        title: str | None = None,
    ) -> dict:
        """落地一次分集切分。"""
        project_dir = self.pm.get_project_path(project_name)
        # 路徑安全：source_rel 必須落在 project_dir/source/ 內
        src_abs = (project_dir / source_rel).resolve()
        source_dir = (project_dir / "source").resolve()
        if not src_abs.is_relative_to(source_dir):
            raise ValueError(f"source 路徑超出 source/ 目錄: {source_rel}")
        source_dir.mkdir(parents=True, exist_ok=True)

        (source_dir / f"episode_{episode}.txt").write_text(part_before, encoding="utf-8")
        (source_dir / "_remaining.txt").write_text(part_after, encoding="utf-8")

        project = self.pm.load_project(project_name)
        episodes = project.setdefault("episodes", [])
        existing: dict | None = next((ep for ep in episodes if int(ep.get("episode", -1)) == int(episode)), None)
        if existing is None:
            existing = {"episode": int(episode), "order": _next_display_order(episodes)}
            episodes.append(existing)
        if title is not None:
            existing["title"] = title
        episodes.sort(key=lambda ep: int(ep.get("episode", 0)))
        self.pm.save_project(project_name, project)
        logger.info(
            "分集切分落地: episode %d，前半 %d 字元，後半 %d 字元",
            episode,
            len(part_before),
            len(part_after),
        )
        return project
