"""tests/test_resource_rename.py — rename_resource 邏輯測試"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.resource_rename import rename_resource


def _make_project(tmp_path: Path) -> tuple[Path, dict]:
    """建立一個含角色/道具/劇本/版本的最小專案。"""
    project_path = tmp_path / "demo"
    (project_path / "characters").mkdir(parents=True)
    (project_path / "characters" / "refs").mkdir()
    (project_path / "clues").mkdir()
    (project_path / "scenes").mkdir()
    (project_path / "scenes" / "refs").mkdir()
    (project_path / "scripts").mkdir()
    (project_path / "versions" / "characters").mkdir(parents=True)
    (project_path / "versions" / "clues").mkdir(parents=True)
    (project_path / "versions" / "scenes").mkdir(parents=True)

    # Files
    (project_path / "characters" / "拉拉布.png").write_bytes(b"png")
    (project_path / "characters" / "refs" / "拉拉布.jpg").write_bytes(b"ref")
    (project_path / "clues" / "玉佩.png").write_bytes(b"clue")
    (project_path / "scenes" / "古城.png").write_bytes(b"scene")
    (project_path / "scenes" / "refs" / "古城.jpg").write_bytes(b"scene-ref")
    (project_path / "versions" / "characters" / "拉拉布_v1_20260101T000000.png").write_bytes(b"v1")
    (project_path / "versions" / "characters" / "拉拉布_v2_20260101T010000.png").write_bytes(b"v2")
    (project_path / "versions" / "clues" / "玉佩_v1_20260101T000000.png").write_bytes(b"v1")
    (project_path / "versions" / "scenes" / "古城_v1_20260101T000000.png").write_bytes(b"v1")

    # versions.json
    (project_path / "versions" / "versions.json").write_text(
        json.dumps(
            {"characters": ["拉拉布", "其他人"], "clues": ["玉佩"], "scenes": ["古城"]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # Script with references (narration mode)
    (project_path / "scripts" / "episode_1.json").write_text(
        json.dumps(
            {
                "episode": 1,
                "title": "T",
                "content_mode": "narration",
                "segments": [
                    {
                        "segment_id": "E1S1",
                        "characters_in_segment": ["拉拉布", "其他人"],
                        "clues_in_segment": ["玉佩"],
                        "scene_in_segment": "古城",
                        "video_prompt": {
                            "action": "x",
                            "dialogue": [
                                {"speaker": "拉拉布", "line": "嗨"},
                                {"speaker": "其他人", "line": "嗯"},
                            ],
                        },
                    },
                    {
                        "segment_id": "E1S2",
                        "characters_in_segment": ["拉拉布"],
                        "clues_in_segment": [],
                        "video_prompt": {"action": "y", "dialogue": []},
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    project = {
        "characters": {
            "拉拉布": {
                "description": "金髮",
                "voice_style": "輕浮",
                "character_sheet": "characters/拉拉布.png",
                "reference_image": "characters/refs/拉拉布.jpg",
            },
            "其他人": {"description": "x", "voice_style": "", "character_sheet": ""},
        },
        "clues": {
            "玉佩": {
                "description": "綠色",
                "importance": "major",
                "clue_sheet": "clues/玉佩.png",
            }
        },
        "scenes": {
            "古城": {
                "description": "城牆",
                "scene_sheet": "scenes/古城.png",
                "scene_ref": "scenes/refs/古城.jpg",
            }
        },
    }
    return project_path, project


def test_rename_character_full_flow(tmp_path: Path):
    project_path, project = _make_project(tmp_path)

    result = rename_resource(project_path, project, "character", "拉拉布", "拉布")

    assert result.files_moved == 4  # main + ref + 2 versions
    assert result.scripts_updated == 1
    assert result.versions_updated == 1

    # project dict
    assert "拉拉布" not in project["characters"]
    assert "拉布" in project["characters"]
    assert project["characters"]["拉布"]["character_sheet"] == "characters/拉布.png"
    assert project["characters"]["拉布"]["reference_image"] == "characters/refs/拉布.jpg"
    assert project["characters"]["其他人"]["description"] == "x"  # 不影響其他

    # 檔案
    assert (project_path / "characters" / "拉布.png").exists()
    assert not (project_path / "characters" / "拉拉布.png").exists()
    assert (project_path / "characters" / "refs" / "拉布.jpg").exists()
    assert (project_path / "versions" / "characters" / "拉布_v1_20260101T000000.png").exists()
    assert (project_path / "versions" / "characters" / "拉布_v2_20260101T010000.png").exists()

    # versions.json
    versions = json.loads((project_path / "versions" / "versions.json").read_text(encoding="utf-8"))
    assert versions["characters"] == ["拉布", "其他人"]
    assert versions["clues"] == ["玉佩"]

    # script 引用
    script = json.loads((project_path / "scripts" / "episode_1.json").read_text(encoding="utf-8"))
    seg1 = script["segments"][0]
    assert seg1["characters_in_segment"] == ["拉布", "其他人"]
    assert seg1["clues_in_segment"] == ["玉佩"]  # 不應動到
    assert seg1["video_prompt"]["dialogue"][0]["speaker"] == "拉布"
    assert seg1["video_prompt"]["dialogue"][1]["speaker"] == "其他人"
    assert script["segments"][1]["characters_in_segment"] == ["拉布"]


def test_rename_clue_full_flow(tmp_path: Path):
    project_path, project = _make_project(tmp_path)

    result = rename_resource(project_path, project, "clue", "玉佩", "青玉碎片")

    assert result.files_moved == 2
    assert result.scripts_updated == 1
    assert result.versions_updated == 1

    assert "玉佩" not in project["clues"]
    assert project["clues"]["青玉碎片"]["clue_sheet"] == "clues/青玉碎片.png"

    assert (project_path / "clues" / "青玉碎片.png").exists()
    assert not (project_path / "clues" / "玉佩.png").exists()

    script = json.loads((project_path / "scripts" / "episode_1.json").read_text(encoding="utf-8"))
    assert script["segments"][0]["clues_in_segment"] == ["青玉碎片"]
    # 角色和對話不該被影響
    assert script["segments"][0]["characters_in_segment"] == ["拉拉布", "其他人"]
    assert script["segments"][0]["video_prompt"]["dialogue"][0]["speaker"] == "拉拉布"


def test_rename_clue_updates_base_version_paths(tmp_path: Path):
    project_path = tmp_path / "demo"
    (project_path / "clues" / "refs").mkdir(parents=True)
    (project_path / "versions" / "clues").mkdir(parents=True)
    (project_path / "scripts").mkdir()
    (project_path / "clues" / "refs" / "舊道具.jpg").write_bytes(b"ref")
    (project_path / "versions" / "clues" / "舊道具_v0.png").write_bytes(b"v0")
    (project_path / "versions" / "clues" / "舊道具_v1_20260101T000000.png").write_bytes(b"v1")
    (project_path / "versions" / "versions.json").write_text(
        json.dumps(
            {
                "clues": {
                    "舊道具": {
                        "current_version": 0,
                        "versions": [
                            {"version": 0, "file": "versions/clues/舊道具_v0.png"},
                            {"version": 1, "file": "versions/clues/舊道具_v1_20260101T000000.png"},
                        ],
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    project = {
        "clues": {
            "舊道具": {
                "description": "x",
                "importance": "major",
                "clue_sheet": "versions/clues/舊道具_v0.png",
                "reference_image": "clues/refs/舊道具.jpg",
            }
        }
    }

    result = rename_resource(project_path, project, "clue", "舊道具", "新道具")

    assert result.files_moved == 3
    assert project["clues"]["新道具"]["clue_sheet"] == "versions/clues/新道具_v0.png"
    assert project["clues"]["新道具"]["reference_image"] == "clues/refs/新道具.jpg"
    assert (project_path / "versions" / "clues" / "新道具_v0.png").exists()
    assert not (project_path / "versions" / "clues" / "舊道具_v0.png").exists()

    versions = json.loads((project_path / "versions" / "versions.json").read_text(encoding="utf-8"))
    assert "舊道具" not in versions["clues"]
    assert versions["clues"]["新道具"]["current_version"] == 0
    assert versions["clues"]["新道具"]["versions"][0]["file"] == "versions/clues/新道具_v0.png"
    assert versions["clues"]["新道具"]["versions"][1]["file"] == "versions/clues/新道具_v1_20260101T000000.png"


def test_rename_scene_full_flow(tmp_path: Path):
    project_path, project = _make_project(tmp_path)

    result = rename_resource(project_path, project, "scene", "古城", "夜市")

    assert result.files_moved == 3
    assert result.scripts_updated == 1
    assert result.versions_updated == 1

    assert "古城" not in project["scenes"]
    assert project["scenes"]["夜市"]["scene_sheet"] == "scenes/夜市.png"
    assert project["scenes"]["夜市"]["scene_ref"] == "scenes/refs/夜市.jpg"

    assert (project_path / "scenes" / "夜市.png").exists()
    assert not (project_path / "scenes" / "古城.png").exists()
    assert (project_path / "scenes" / "refs" / "夜市.jpg").exists()
    assert (project_path / "versions" / "scenes" / "夜市_v1_20260101T000000.png").exists()

    versions = json.loads((project_path / "versions" / "versions.json").read_text(encoding="utf-8"))
    assert versions["scenes"] == ["夜市"]

    script = json.loads((project_path / "scripts" / "episode_1.json").read_text(encoding="utf-8"))
    assert script["segments"][0]["scene_in_segment"] == "夜市"


def test_rename_same_name_is_noop(tmp_path: Path):
    project_path, project = _make_project(tmp_path)
    result = rename_resource(project_path, project, "character", "拉拉布", "拉拉布")
    assert result.files_moved == 0
    assert "拉拉布" in project["characters"]


def test_rename_to_existing_raises(tmp_path: Path):
    project_path, project = _make_project(tmp_path)
    with pytest.raises(ValueError, match="已存在"):
        rename_resource(project_path, project, "character", "拉拉布", "其他人")
    # 沒搬東西
    assert (project_path / "characters" / "拉拉布.png").exists()
    assert (
        project_path / "characters" / "其他人.png" if False else project_path / "characters" / "拉拉布.png"
    ).exists()


def test_rename_unknown_old_raises(tmp_path: Path):
    project_path, project = _make_project(tmp_path)
    with pytest.raises(KeyError):
        rename_resource(project_path, project, "character", "不存在", "新名")


def test_rename_invalid_new_name(tmp_path: Path):
    project_path, project = _make_project(tmp_path)
    for bad in ["", "  ", "a/b", "a\\b", "a:b", "."]:
        with pytest.raises(ValueError):
            rename_resource(project_path, project, "character", "拉拉布", bad)
    # 檔案還在原處
    assert (project_path / "characters" / "拉拉布.png").exists()


def test_rename_target_file_collision(tmp_path: Path):
    """目標檔案已存在但 project dict 沒記錄 → 拒絕，不覆蓋。"""
    project_path, project = _make_project(tmp_path)
    # 偷偷放一個會衝突的目標檔
    (project_path / "characters" / "拉布.png").write_bytes(b"orphan")
    with pytest.raises(ValueError, match="目標檔案已存在"):
        rename_resource(project_path, project, "character", "拉拉布", "拉布")
    # 原本檔案沒動
    assert (project_path / "characters" / "拉拉布.png").exists()
    assert (project_path / "characters" / "拉布.png").read_bytes() == b"orphan"


def test_rename_drama_mode_script(tmp_path: Path):
    """drama 模式劇本用 scenes / characters_in_scene / clues_in_scene。"""
    project_path, project = _make_project(tmp_path)
    # 替換為 drama 結構
    (project_path / "scripts" / "episode_1.json").write_text(
        json.dumps(
            {
                "episode": 1,
                "content_mode": "drama",
                "scenes": [
                    {
                        "scene_id": "E1S1",
                        "characters_in_scene": ["拉拉布"],
                        "clues_in_scene": ["玉佩"],
                        "video_prompt": {
                            "action": "x",
                            "dialogue": [{"speaker": "拉拉布", "line": "嗨"}],
                        },
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    rename_resource(project_path, project, "character", "拉拉布", "拉布")
    script = json.loads((project_path / "scripts" / "episode_1.json").read_text(encoding="utf-8"))
    assert script["scenes"][0]["characters_in_scene"] == ["拉布"]
    assert script["scenes"][0]["video_prompt"]["dialogue"][0]["speaker"] == "拉布"
