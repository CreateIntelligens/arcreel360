from pathlib import Path

import pytest

from lib.project_paths import ProjectPaths
from lib.project_store import ProjectStore
from lib.script_repository import ScriptRepository


@pytest.fixture
def repo(tmp_path: Path) -> ScriptRepository:
    root = tmp_path / "projects"
    (root / "demo" / "scripts").mkdir(parents=True)
    paths = ProjectPaths(root)
    store = ProjectStore(paths)
    return ScriptRepository(paths=paths, store=store, sync_characters=lambda *a: None, sync_clues=lambda *a: None)


def test_create_and_load_script(repo: ScriptRepository):
    script = repo.create_script("demo", title="T", chapter="C1")
    repo.save_script("demo", script)
    scripts = repo.list_scripts("demo")
    assert len(scripts) == 1


def test_get_scenes_needing_storyboard_filters_done(repo: ScriptRepository):
    repo.save_script(
        "demo",
        {
            "content_mode": "narration",
            "segments": [
                {"segment_id": "s1", "generated_assets": {"storyboard_image": "x.png"}},
                {"segment_id": "s2", "generated_assets": {}},
            ],
        },
        "ep1.json",
    )
    pending = repo.get_scenes_needing_storyboard("demo", "ep1.json")
    assert [s["segment_id"] for s in pending] == ["s2"]
