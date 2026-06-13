"""ProjectManager.reorder_episodes 與相關 ``order`` 欄位行為的單元測試。"""

from __future__ import annotations

from pathlib import Path

import pytest

from lib.project_manager import ProjectManager


def _setup(tmp_path: Path) -> ProjectManager:
    pm = ProjectManager(tmp_path / "projects")
    pm.create_project("demo")
    pm.create_project_metadata("demo", "Demo", "Anime", "narration")
    for ep in (1, 2, 3):
        pm.add_episode("demo", ep, f"第 {ep} 集", f"scripts/episode_{ep}.json")
    return pm


def _orders_by_episode(project: dict) -> dict[int, int]:
    return {ep["episode"]: ep["order"] for ep in project["episodes"]}


class TestReorderEpisodes:
    def test_new_episodes_get_dense_order_in_creation_sequence(self, tmp_path):
        pm = _setup(tmp_path)
        project = pm.load_project("demo")
        assert _orders_by_episode(project) == {1: 0, 2: 1, 3: 2}

    def test_reorder_assigns_new_order_values(self, tmp_path):
        pm = _setup(tmp_path)
        updated = pm.reorder_episodes("demo", [3, 1, 2])

        assert _orders_by_episode(updated) == {3: 0, 1: 1, 2: 2}
        # 持久化檢查
        reloaded = pm.load_project("demo")
        assert _orders_by_episode(reloaded) == {3: 0, 1: 1, 2: 2}

    def test_reorder_mismatch_raises_value_error(self, tmp_path):
        pm = _setup(tmp_path)
        # 少一集
        with pytest.raises(ValueError):
            pm.reorder_episodes("demo", [1, 2])
        # 多一集
        with pytest.raises(ValueError):
            pm.reorder_episodes("demo", [1, 2, 3, 4])
        # 集合相同但有重複
        with pytest.raises(ValueError):
            pm.reorder_episodes("demo", [1, 1, 2])

    def test_new_episode_after_reorder_lands_at_end(self, tmp_path):
        pm = _setup(tmp_path)
        pm.reorder_episodes("demo", [3, 1, 2])  # order 變成 {3:0, 1:1, 2:2}
        pm.add_episode("demo", 4, "第 4 集", "scripts/episode_4.json")
        project = pm.load_project("demo")
        assert _orders_by_episode(project)[4] == 3  # max(0,1,2) + 1

    def test_remove_then_add_skips_freed_order_value(self, tmp_path):
        pm = _setup(tmp_path)
        # 預設 order: {1:0, 2:1, 3:2}
        pm.remove_episode("demo", 2)
        pm.add_episode("demo", 4, "第 4 集", "scripts/episode_4.json")
        project = pm.load_project("demo")
        # 移除 2 並不會壓縮 order；新加的 4 落到 max(0,2) + 1 = 3
        assert _orders_by_episode(project) == {1: 0, 3: 2, 4: 3}
