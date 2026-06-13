"""ProjectManager.remove_episode 的單元測試。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.project_manager import ProjectManager


def _write(path: Path, text: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _setup_project_with_two_episodes(tmp_path: Path) -> ProjectManager:
    pm = ProjectManager(tmp_path / "projects")
    project_dir = pm.create_project("demo")
    pm.create_project_metadata("demo", "Demo", "Anime", "narration")

    for ep in (1, 2):
        pm.add_episode("demo", ep, f"第 {ep} 集", f"scripts/episode_{ep}.json")
        pm.save_script(
            "demo",
            {
                "episode": ep,
                "title": f"第 {ep} 集",
                "content_mode": "narration",
                "segments": [{"segment_id": f"E{ep}S1"}, {"segment_id": f"E{ep}S2"}],
            },
            f"episode_{ep}.json",
        )
        for sid in (f"E{ep}S1", f"E{ep}S2"):
            _write(project_dir / "storyboards" / f"scene_{sid}.png")
            _write(project_dir / "videos" / f"scene_{sid}.mp4")
            _write(project_dir / "thumbnails" / f"scene_{sid}.png")
            _write(project_dir / "versions" / "storyboards" / f"{sid}_v1_20240101_000000.png")
            _write(project_dir / "versions" / "videos" / f"{sid}_v1_20240101_000000.mp4")
        _write(project_dir / "drafts" / f"episode_{ep}" / "step1_segments.md", "draft")
        _write(project_dir / "source" / f"episode_{ep}.txt", "source")
        _write(project_dir / "output" / f"episode_{ep}.mp4")

    versions_file = project_dir / "versions" / "versions.json"
    _write(
        versions_file,
        json.dumps(
            {
                "storyboards": {f"E{ep}S1": {"current_version": 1, "versions": []} for ep in (1, 2)},
                "videos": {f"E{ep}S1": {"current_version": 1, "versions": []} for ep in (1, 2)},
                "characters": {},
                "clues": {},
            }
        ),
    )
    return pm


class TestRemoveEpisode:
    def test_removes_all_episode_scoped_artifacts(self, tmp_path):
        pm = _setup_project_with_two_episodes(tmp_path)
        project_dir = pm.get_project_path("demo")

        project, removed = pm.remove_episode("demo", 1)

        # project.json: E1 移除、E2 保留
        episode_numbers = [ep["episode"] for ep in project["episodes"]]
        assert episode_numbers == [2]
        assert [ep["episode"] for ep in pm.load_project("demo")["episodes"]] == [2]

        # E1 的檔案全數消失
        assert not (project_dir / "scripts" / "episode_1.json").exists()
        assert not (project_dir / "drafts" / "episode_1").exists()
        assert not (project_dir / "source" / "episode_1.txt").exists()
        assert not (project_dir / "output" / "episode_1.mp4").exists()
        for sid in ("E1S1", "E1S2"):
            assert not (project_dir / "storyboards" / f"scene_{sid}.png").exists()
            assert not (project_dir / "videos" / f"scene_{sid}.mp4").exists()
            assert not (project_dir / "thumbnails" / f"scene_{sid}.png").exists()
            assert not (project_dir / "versions" / "storyboards" / f"{sid}_v1_20240101_000000.png").exists()
            assert not (project_dir / "versions" / "videos" / f"{sid}_v1_20240101_000000.mp4").exists()

        # E2 的檔案完好
        assert (project_dir / "scripts" / "episode_2.json").exists()
        assert (project_dir / "drafts" / "episode_2" / "step1_segments.md").exists()
        assert (project_dir / "output" / "episode_2.mp4").exists()
        for sid in ("E2S1", "E2S2"):
            assert (project_dir / "storyboards" / f"scene_{sid}.png").exists()
            assert (project_dir / "videos" / f"scene_{sid}.mp4").exists()

        # versions.json：移除 E1*，保留 E2*
        vdata = json.loads((project_dir / "versions" / "versions.json").read_text(encoding="utf-8"))
        assert set(vdata["storyboards"].keys()) == {"E2S1"}
        assert set(vdata["videos"].keys()) == {"E2S1"}

        # removed 清單涵蓋主要項目
        assert "scripts/episode_1.json" in removed
        assert "drafts/episode_1/" in removed
        assert "storyboards/scene_E1S1.png" in removed
        assert "versions/versions.json" in removed

    def test_missing_episode_raises_keyerror(self, tmp_path):
        pm = _setup_project_with_two_episodes(tmp_path)
        with pytest.raises(KeyError):
            pm.remove_episode("demo", 99)

    def test_falls_back_to_prefix_scan_when_script_unreadable(self, tmp_path):
        pm = _setup_project_with_two_episodes(tmp_path)
        project_dir = pm.get_project_path("demo")
        # 弄壞 E1 的劇本檔，remove_episode 仍須靠 "E1S" 前綴清掉媒體
        (project_dir / "scripts" / "episode_1.json").write_text("{ not json", encoding="utf-8")

        pm.remove_episode("demo", 1)

        assert not (project_dir / "storyboards" / "scene_E1S1.png").exists()
        assert not (project_dir / "storyboards" / "scene_E1S2.png").exists()
        assert (project_dir / "storyboards" / "scene_E2S1.png").exists()
