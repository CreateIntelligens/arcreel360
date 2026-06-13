"""遷移腳本測試：location clue → scene。"""

import json
from pathlib import Path

from scripts.migrate_location_clues_to_scenes import migrate_project


def _write_project(tmp_path: Path, data: dict) -> Path:
    pdir = tmp_path / "proj"
    pdir.mkdir()
    (pdir / "project.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return pdir


def test_location_clue_moved_to_scenes(tmp_path):
    pdir = _write_project(
        tmp_path,
        {
            "clues": {
                "鏽鐵區": {
                    "type": "location",
                    "description": "破敗的工業區",
                    "importance": "major",
                    "clue_sheet": "assets/clue.png",
                    "reference_image": "assets/ref.png",
                },
                "鑰匙": {"type": "prop", "description": "黃銅鑰匙", "importance": "minor"},
            },
            "scenes": {},
        },
    )

    report = migrate_project(pdir)

    data = json.loads((pdir / "project.json").read_text(encoding="utf-8"))
    assert "鏽鐵區" not in data["clues"]
    assert "鑰匙" in data["clues"]
    assert data["scenes"]["鏽鐵區"] == {
        "description": "破敗的工業區",
        "scene_sheet": "assets/clue.png",
        "scene_ref": "assets/ref.png",
    }
    assert report.migrated == ["鏽鐵區"]
    assert report.conflicts == []


def test_name_conflict_skipped_with_warning(tmp_path):
    pdir = _write_project(
        tmp_path,
        {
            "clues": {"鏽鐵區": {"type": "location", "description": "工業區", "importance": "major"}},
            "scenes": {"鏽鐵區": {"description": "既有場景", "scene_sheet": "", "scene_ref": ""}},
        },
    )

    report = migrate_project(pdir)

    data = json.loads((pdir / "project.json").read_text(encoding="utf-8"))
    assert "鏽鐵區" in data["clues"]  # 衝突 → 保留 clue
    assert data["scenes"]["鏽鐵區"]["description"] == "既有場景"  # 不覆寫
    assert report.migrated == []
    assert report.conflicts == ["鏽鐵區"]


def test_idempotent_when_no_location_clue(tmp_path):
    pdir = _write_project(
        tmp_path,
        {"clues": {"鑰匙": {"type": "prop", "description": "鑰匙", "importance": "minor"}}, "scenes": {}},
    )

    report = migrate_project(pdir)

    assert report.migrated == []
    assert report.conflicts == []


def test_script_clue_reference_moved_to_scene(tmp_path):
    pdir = _write_project(
        tmp_path,
        {
            "clues": {"鏽鐵區": {"type": "location", "description": "工業區", "importance": "major"}},
            "scenes": {},
        },
    )
    scripts_dir = pdir / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "episode_1.json").write_text(
        json.dumps(
            {
                "segments": [
                    {
                        "segment_id": "E1S1",
                        "clues_in_segment": ["鏽鐵區", "鑰匙"],
                        "scene_in_segment": None,
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    migrate_project(pdir)

    script = json.loads((scripts_dir / "episode_1.json").read_text(encoding="utf-8"))
    seg = script["segments"][0]
    assert seg["clues_in_segment"] == ["鑰匙"]
    assert seg["scene_in_segment"] == "鏽鐵區"


def test_script_multi_location_conflict_keeps_first(tmp_path):
    pdir = _write_project(
        tmp_path,
        {
            "clues": {
                "鏽鐵區": {"type": "location", "description": "A", "importance": "major"},
                "書房": {"type": "location", "description": "B", "importance": "major"},
            },
            "scenes": {},
        },
    )
    scripts_dir = pdir / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "episode_1.json").write_text(
        json.dumps(
            {
                "segments": [
                    {
                        "segment_id": "E1S1",
                        "clues_in_segment": ["鏽鐵區", "書房"],
                        "scene_in_segment": None,
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report = migrate_project(pdir)

    script = json.loads((scripts_dir / "episode_1.json").read_text(encoding="utf-8"))
    seg = script["segments"][0]
    assert seg["scene_in_segment"] == "鏽鐵區"  # 填第一個
    assert seg["clues_in_segment"] == []  # 兩個都從 clues 移除
    assert "E1S1" in report.script_warnings[0]  # 其餘印警告
