from pathlib import Path

import pytest

from lib.project_paths import ProjectPaths
from lib.project_store import ProjectStore


@pytest.fixture
def store(tmp_path: Path) -> ProjectStore:
    root = tmp_path / "projects"
    root.mkdir()
    (root / "demo").mkdir()
    return ProjectStore(ProjectPaths(root))


def test_save_then_load_roundtrip(store: ProjectStore):
    store.save_project("demo", {"name": "demo", "episodes": []})
    loaded = store.load_project("demo")
    assert loaded["name"] == "demo"


def test_atomic_write_does_not_leave_tmp(store: ProjectStore, tmp_path: Path):
    store.save_project("demo", {"name": "demo"})
    leftovers = list((tmp_path / "projects" / "demo").glob(".project.*.tmp"))
    assert leftovers == []


def test_update_project_applies_mutation(store: ProjectStore):
    store.save_project("demo", {"name": "demo", "title": "old"})
    store.update_project("demo", lambda p: p.__setitem__("title", "new"))
    assert store.load_project("demo")["title"] == "new"
