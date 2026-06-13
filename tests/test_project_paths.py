from pathlib import Path

import pytest

from lib.project_paths import ProjectPaths


def test_get_project_path_under_root(tmp_path: Path):
    (tmp_path / "demo").mkdir()
    paths = ProjectPaths(tmp_path)
    assert paths.get_project_path("demo") == tmp_path / "demo"


def test_get_project_path_missing_raises(tmp_path: Path):
    paths = ProjectPaths(tmp_path)
    with pytest.raises(FileNotFoundError):
        paths.get_project_path("nope")


def test_subpaths_compose_correctly(tmp_path: Path):
    (tmp_path / "demo").mkdir()
    paths = ProjectPaths(tmp_path)
    assert paths.get_source_path("demo", "a.txt") == tmp_path / "demo" / "source" / "a.txt"
    assert paths.get_storyboard_path("demo", "s.png") == tmp_path / "demo" / "storyboards" / "s.png"
    assert paths.get_video_path("demo", "v.mp4") == tmp_path / "demo" / "videos" / "v.mp4"
    assert paths.get_character_path("demo", "c.png") == tmp_path / "demo" / "characters" / "c.png"
    assert paths.get_output_path("demo", "o.mp4") == tmp_path / "demo" / "output" / "o.mp4"
    assert paths.get_clue_path("demo", "k.png") == tmp_path / "demo" / "clues" / "k.png"
    assert paths.get_scene_path("demo", "sc.png") == tmp_path / "demo" / "scenes" / "sc.png"


def test_get_project_file_path(tmp_path: Path):
    (tmp_path / "demo").mkdir()
    paths = ProjectPaths(tmp_path)
    assert paths._get_project_file_path("demo") == tmp_path / "demo" / "project.json"


def test_normalize_project_name_rejects_unsafe():
    with pytest.raises(ValueError):
        ProjectPaths.normalize_project_name("../evil")


def test_normalize_project_name_passes_valid():
    assert ProjectPaths.normalize_project_name("my-demo-01") == "my-demo-01"


def test_safe_subpath_rejects_traversal(tmp_path: Path):
    paths = ProjectPaths(tmp_path)
    with pytest.raises(ValueError):
        paths._safe_subpath(tmp_path / "demo", "../../etc/passwd")


def test_slugify_project_title():
    assert ProjectPaths._slugify_project_title("Hello World!") == "hello-world"
    assert ProjectPaths._slugify_project_title("") == "project"
