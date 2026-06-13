from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

from lib.project_manager import ProjectManager

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "agent_runtime_profile"
    / ".claude"
    / "skills"
    / "compose-video"
    / "scripts"
    / "compose_video.py"
)


def load_module() -> Any:
    spec = importlib.util.spec_from_file_location("test_compose_video_script_module", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_compose_video_supports_narration_segments(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    projects_root = tmp_path / "projects"
    project_name = "demo"
    pm = ProjectManager(projects_root=str(projects_root))
    project_dir = pm.create_project(project_name)
    pm.save_project(project_name, {"title": "Demo"})

    (project_dir / "videos" / "scene_E1S1.mp4").write_bytes(b"video")
    (project_dir / "scripts" / "episode_1.json").write_text(
        json.dumps(
            {
                "content_mode": "narration",
                "novel": {"chapter": "第一章"},
                "segments": [
                    {
                        "segment_id": "E1S1",
                        "transition_to_next": "cut",
                        "generated_assets": {"video_clip": "videos/scene_E1S1.mp4"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    captured: dict[str, Any] = {}

    def fake_concatenate_simple(video_paths: list[Path], output_path: Path) -> None:
        captured["video_paths"] = video_paths
        captured["output_path"] = output_path
        output_path.write_bytes(b"final")

    monkeypatch.chdir(project_dir)
    monkeypatch.setattr(module, "concatenate_simple", fake_concatenate_simple)

    output_path = module.compose_video("episode_1.json", "episode_1_final.mp4", use_transitions=False)

    assert captured["video_paths"] == [project_dir / "videos" / "scene_E1S1.mp4"]
    assert output_path == project_dir / "output" / "episode_1_final.mp4"
    assert output_path.read_bytes() == b"final"
