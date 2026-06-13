"""``server.agent_runtime.skill_function_declarations`` 单元测试。

覆盖：
- 注册表完整性（workflow skill 都有 declaration + handler）
- 输入校验：缺字段 / 错类型 / 空数组拒绝
- generate_characters / generate_clues 正常写入 project.json
- manga_workflow_status 各阶段判断
- 资产 skill（generate_storyboard / generate_video / compose_video）前置条件与入队行为
- run_subagent dispatch 与 unknown_skill 处理
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from lib.project_manager import ProjectManager
from server.agent_runtime.skill_function_declarations import (
    SKILL_DECLARATIONS,
    SKILL_HANDLERS,
    FunctionDeclaration,
    SkillCallContext,
    get_skill_names,
    run_subagent,
)
from server.agent_runtime.tool_sandbox import ToolSandbox

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    return tmp_path / "projects"


@pytest.fixture
def project_manager(project_root: Path) -> ProjectManager:
    project_root.mkdir(parents=True, exist_ok=True)
    return ProjectManager(projects_root=str(project_root))


@pytest.fixture
def project_name(project_manager: ProjectManager) -> str:
    name = "demo"
    project_manager.create_project(name)
    project_manager.save_project(
        name,
        {
            "title": "Demo",
            "content_mode": "narration",
            "style": "anime",
            "characters": {},
            "clues": {},
            "episodes": [],
        },
    )
    return name


def write_minimal_overview(project_manager: ProjectManager, project_name: str) -> None:
    def mutate(project: dict[str, Any]) -> None:
        project["overview"] = {
            "synopsis": "故事",
            "genre": "奇幻",
            "theme": "成長",
            "world_setting": "架空世界",
        }

    project_manager.update_project(project_name, mutate)


@pytest.fixture
def context(project_root: Path, project_manager: ProjectManager, project_name: str) -> SkillCallContext:
    sandbox = ToolSandbox(project_root=project_root, project_name=project_name)
    return SkillCallContext(
        project_name=project_name,
        sandbox=sandbox,
        project_manager=project_manager,
        session_id="gemini-full:test123",
    )


# ---------------------------------------------------------------------------
# 注册表完整性
# ---------------------------------------------------------------------------


def test_workflow_skills_registered() -> None:
    assert set(SKILL_HANDLERS.keys()) == {
        "peek_split_point",
        "split_episode",
        "preprocess_episode",
        "generate_overview",
        "update_overview",
        "generate_script",
        "generate_characters",
        "generate_clues",
        "generate_scenes",
        "generate_character_sheets",
        "generate_clue_sheets",
        "generate_scene_sheets",
        "update_character",
        "update_clue",
        "update_scene",
        "update_video_settings",
        "rename_entity",
        "delete_entity",
        "manga_workflow_status",
        "generate_storyboard",
        "generate_video",
        "compose_video",
    }


def test_each_handler_has_declaration() -> None:
    decl_names = {d.name for d in SKILL_DECLARATIONS}
    assert decl_names == set(SKILL_HANDLERS.keys())


def test_declarations_are_valid_function_declaration() -> None:
    for decl in SKILL_DECLARATIONS:
        assert isinstance(decl, FunctionDeclaration)
        assert decl.name and decl.description
        assert isinstance(decl.parameters, dict)
        assert decl.parameters.get("type") == "object"


def test_to_gemini_returns_plain_dict() -> None:
    decl = SKILL_DECLARATIONS[0]
    payload = decl.to_gemini()
    assert payload == {
        "name": decl.name,
        "description": decl.description,
        "parameters": decl.parameters,
    }


def test_get_skill_names_matches_registry() -> None:
    assert sorted(get_skill_names()) == sorted(SKILL_HANDLERS.keys())


# ---------------------------------------------------------------------------
# generate_characters
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_overview_writes_structured_overview(
    context: SkillCallContext,
    project_manager: ProjectManager,
    project_name: str,
) -> None:
    result = await run_subagent(
        context,
        "update_overview",
        {
            "synopsis": "拉布揭開鎏金城背後的深淵交易。",
            "genre": "黑暗奇幻",
            "theme": "反抗與覺醒",
            "world_setting": "鎏金城由貴族區和平民區割裂，刀盾幣與深淵封印共同支配秩序。",
        },
    )

    assert result["ok"] is True
    assert result["overview"]["world_setting"].startswith("鎏金城")
    saved = project_manager.load_project(project_name)
    assert saved["overview"] == result["overview"]


@pytest.mark.asyncio
async def test_generate_overview_delegates_to_project_manager(
    context: SkillCallContext,
    project_manager: ProjectManager,
    project_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generated = {
        "synopsis": "故事梗概",
        "genre": "懸疑",
        "theme": "真相",
        "world_setting": "現代都市",
        "generated_at": "2026-05-22T00:00:00",
    }

    async def fake_generate_overview(name: str) -> dict[str, str]:
        assert name == project_name
        project = project_manager.load_project(name)
        project["overview"] = generated
        project_manager.save_project(name, project)
        return generated

    monkeypatch.setattr(project_manager, "generate_overview", fake_generate_overview)

    result = await run_subagent(context, "generate_overview", {})

    assert result == {"ok": True, "overview": generated}
    assert project_manager.load_project(project_name)["overview"] == generated


@pytest.mark.asyncio
async def test_generate_characters_writes_to_project_json(
    context: SkillCallContext, project_manager: ProjectManager, project_name: str
) -> None:
    result = await run_subagent(
        context,
        "generate_characters",
        {
            "characters": [
                {"name": "小明", "description": "一個少年", "voice_style": "清亮"},
                {"name": "小紅", "description": "一個少女"},
            ]
        },
    )
    assert result == {"ok": True, "added": ["小明", "小紅"], "skipped": []}

    project = project_manager.load_project(project_name)
    assert "小明" in project["characters"]
    assert project["characters"]["小明"]["description"] == "一個少年"
    assert project["characters"]["小明"]["voice_style"] == "清亮"


@pytest.mark.asyncio
async def test_generate_characters_skips_invalid(context: SkillCallContext) -> None:
    result = await run_subagent(
        context,
        "generate_characters",
        {
            "characters": [
                {"name": "", "description": "no name"},
                {"name": "valid", "description": ""},
                "not-a-dict",
                {"name": "ok", "description": "ok desc"},
            ]
        },
    )
    assert result["ok"] is True
    assert result["added"] == ["ok"]
    assert len(result["skipped"]) == 3


@pytest.mark.asyncio
async def test_generate_characters_rejects_non_array(context: SkillCallContext) -> None:
    result = await run_subagent(context, "generate_characters", {"characters": "nope"})
    assert result["error"] == "invalid_argument"


# ---------------------------------------------------------------------------
# generate_clues
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_clues_writes_to_project_json(
    context: SkillCallContext, project_manager: ProjectManager, project_name: str
) -> None:
    result = await run_subagent(
        context,
        "generate_clues",
        {
            "clues": [
                {
                    "name": "玉佩",
                    "description": "祖傳玉佩",
                    "importance": "major",
                },
                {
                    "name": "銅鑰匙",
                    "description": "帶有刻痕的黃銅鑰匙",
                },
            ]
        },
    )
    assert result["ok"] is True
    assert "玉佩" in result["added"]
    assert "銅鑰匙" in result["added"]

    project = project_manager.load_project(project_name)
    assert project["clues"]["玉佩"]["importance"] == "major"
    assert project["clues"]["銅鑰匙"]["importance"] == "minor"


@pytest.mark.asyncio
async def test_generate_clues_dedup_existing(
    context: SkillCallContext, project_manager: ProjectManager, project_name: str
) -> None:
    project_manager.add_clue(project_name, "玉佩", "舊定義", "minor")
    result = await run_subagent(
        context,
        "generate_clues",
        {
            "clues": [
                {"name": "玉佩", "description": "重複定義"},
            ]
        },
    )
    assert result["added"] == []
    assert result["skipped"][0]["reason"] == "already exists"


@pytest.mark.asyncio
async def test_generate_clues_rejects_missing_fields(context: SkillCallContext) -> None:
    result = await run_subagent(
        context,
        "generate_clues",
        {
            "clues": [
                {"name": "x"},
            ]
        },
    )
    assert result["added"] == []
    assert len(result["skipped"]) == 1


# ---------------------------------------------------------------------------
# generate_*_sheets
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_character_sheets_enqueues_missing_character_sheets(
    context: SkillCallContext,
    project_manager: ProjectManager,
    project_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_manager.add_project_character(project_name, "小明", "紅衣少年", None)
    project_manager.add_project_character(project_name, "小紅", "藍衣少女", None)

    def set_existing_sheet(project: dict[str, Any]) -> None:
        project["characters"]["小紅"]["character_sheet"] = "characters/小紅.png"
        project["characters"]["小明"]["image_backend"] = "gemini-vertex/imagen-4"

    project_manager.update_project(project_name, set_existing_sheet)

    captured: list[Any] = []

    async def fake_batch(
        project: str, specs: list[Any], on_success: Any, on_failure: Any
    ) -> tuple[list[Any], list[Any]]:
        captured.extend(specs)
        from lib.generation_queue_client import BatchTaskResult

        return [
            BatchTaskResult(
                resource_id=spec.resource_id,
                task_id=f"task-{spec.resource_id}",
                status="succeeded",
                result={"file_path": f"characters/{spec.resource_id}.png"},
            )
            for spec in specs
        ], []

    monkeypatch.setattr(
        "lib.generation_queue_client._batch_enqueue_and_wait",
        fake_batch,
    )

    result = await run_subagent(context, "generate_character_sheets", {})

    assert result["ok"] is True
    assert result["task_type"] == "character"
    assert result["succeeded"] == ["小明"]
    assert result["skipped"] == [{"resource_id": "小紅", "reason": "already_exists"}]
    assert len(captured) == 1
    spec = captured[0]
    assert spec.task_type == "character"
    assert spec.media_type == "image"
    assert spec.resource_id == "小明"
    assert spec.payload == {
        "prompt": "紅衣少年",
        "from_agent": True,
        "image_provider": "gemini-vertex",
        "image_model": "imagen-4",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("skill", "setup_entity", "expected_task_type"),
    [
        ("generate_clue_sheets", "clue", "clue"),
        ("generate_scene_sheets", "scene", "scene"),
    ],
)
async def test_generate_lorebook_sheets_rejects_unknown_names(
    context: SkillCallContext,
    project_manager: ProjectManager,
    project_name: str,
    skill: str,
    setup_entity: str,
    expected_task_type: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if setup_entity == "clue":
        project_manager.add_clue(project_name, "玉佩", "祖傳玉佩", "major")
    else:
        project_manager.add_project_scene(project_name, "古城", "破舊城門")

    async def fake_batch(
        project: str, specs: list[Any], on_success: Any, on_failure: Any
    ) -> tuple[list[Any], list[Any]]:
        return [], []

    monkeypatch.setattr(
        "lib.generation_queue_client._batch_enqueue_and_wait",
        fake_batch,
    )

    result = await run_subagent(context, skill, {"names": ["不存在"]})

    assert result["error"] == "nothing_to_enqueue"
    assert result["task_type"] == expected_task_type
    assert result["skipped"] == [{"resource_id": "不存在", "reason": "not_found"}]


# ---------------------------------------------------------------------------
# manga_workflow_status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_manga_workflow_status_reports_missing_overview_before_assets(
    context: SkillCallContext,
    project_manager: ProjectManager,
    project_name: str,
) -> None:
    project_manager.add_project_character(project_name, "x", "desc", None)

    result = await run_subagent(context, "manga_workflow_status", {"episode": 1})

    assert result["stage"] == 0
    assert "generate_overview" in result["next_action"]


@pytest.mark.asyncio
async def test_manga_workflow_status_stage_1_empty(
    context: SkillCallContext,
    project_manager: ProjectManager,
    project_name: str,
) -> None:
    write_minimal_overview(project_manager, project_name)
    result = await run_subagent(context, "manga_workflow_status", {})
    assert result["stage"] == 1
    assert "全局角色" in result["stage_name"]


@pytest.mark.asyncio
async def test_manga_workflow_status_stage_2_missing_source(
    context: SkillCallContext, project_manager: ProjectManager, project_name: str
) -> None:
    write_minimal_overview(project_manager, project_name)
    project_manager.add_project_character(project_name, "x", "desc", None)
    result = await run_subagent(context, "manga_workflow_status", {"episode": 1})
    assert result["stage"] == 2
    assert "source/episode_1.txt" in result["next_action"]


@pytest.mark.asyncio
async def test_manga_workflow_status_stage_3_missing_step1(
    context: SkillCallContext,
    project_manager: ProjectManager,
    project_name: str,
    project_root: Path,
) -> None:
    write_minimal_overview(project_manager, project_name)
    project_manager.add_project_character(project_name, "x", "desc", None)
    (project_root / project_name / "source" / "episode_1.txt").write_text("text", "utf-8")
    result = await run_subagent(context, "manga_workflow_status", {"episode": 1})
    assert result["stage"] == 3


@pytest.mark.asyncio
async def test_manga_workflow_status_stage_4_missing_script(
    context: SkillCallContext,
    project_manager: ProjectManager,
    project_name: str,
    project_root: Path,
) -> None:
    write_minimal_overview(project_manager, project_name)
    project_manager.add_project_character(project_name, "x", "desc", None)
    pdir = project_root / project_name
    (pdir / "source" / "episode_1.txt").write_text("text", "utf-8")
    (pdir / "drafts" / "episode_1").mkdir(parents=True)
    (pdir / "drafts" / "episode_1" / "step1_segments.md").write_text("# step1", "utf-8")
    result = await run_subagent(context, "manga_workflow_status", {"episode": 1})
    assert result["stage"] == 4
    assert "generate_script" in result["next_action"]


@pytest.mark.asyncio
async def test_manga_workflow_status_stage_5_6_missing_sheets(
    context: SkillCallContext,
    project_manager: ProjectManager,
    project_name: str,
    project_root: Path,
) -> None:
    write_minimal_overview(project_manager, project_name)
    project_manager.add_project_character(project_name, "x", "desc", None)
    project_manager.add_clue(project_name, "y", "desc", "major")
    project_manager.add_project_scene(project_name, "z", "desc")
    pdir = project_root / project_name
    (pdir / "source" / "episode_1.txt").write_text("text", "utf-8")
    (pdir / "drafts" / "episode_1").mkdir(parents=True)
    (pdir / "drafts" / "episode_1" / "step1_segments.md").write_text("md", "utf-8")
    (pdir / "scripts" / "episode_1.json").write_text(json.dumps({"scenes": []}), "utf-8")
    result = await run_subagent(context, "manga_workflow_status", {"episode": 1})
    assert result["stage"] == "5_6"
    assert "generate_character_sheets" in result["next_action"]
    assert "generate_clue_sheets" in result["next_action"]
    assert "generate_scene_sheets" in result["next_action"]
    assert "x" in result["context"]["missing_character_sheets"]
    assert "y" in result["context"]["missing_clue_sheets"]
    assert "z" in result["context"]["missing_scene_sheets"]


@pytest.mark.asyncio
async def test_manga_workflow_status_complete_with_flat_generated_assets(
    context: SkillCallContext,
    project_manager: ProjectManager,
    project_name: str,
    project_root: Path,
) -> None:
    project_manager.save_project(
        project_name,
        {
            "title": "Demo",
            "content_mode": "narration",
            "style": "anime",
            "overview": {
                "synopsis": "故事",
                "genre": "奇幻",
                "theme": "成長",
                "world_setting": "架空世界",
            },
            "characters": {"x": {"description": "desc", "character_sheet": "characters/x.png"}},
            "clues": {},
            "episodes": [{"episode": 1}],
        },
    )
    pdir = project_root / project_name
    (pdir / "source" / "episode_1.txt").write_text("text", "utf-8")
    (pdir / "drafts" / "episode_1").mkdir(parents=True)
    (pdir / "drafts" / "episode_1" / "step1_segments.md").write_text("md", "utf-8")
    (pdir / "storyboards" / "scene_E1S1.png").write_bytes(b"png")
    (pdir / "videos" / "scene_E1S1.mp4").write_bytes(b"mp4")
    (pdir / "scripts" / "episode_1.json").write_text(
        json.dumps(
            {
                "content_mode": "narration",
                "segments": [
                    {
                        "segment_id": "E1S1",
                        "generated_assets": {
                            "storyboard_image": "storyboards/scene_E1S1.png",
                            "video_clip": "videos/scene_E1S1.mp4",
                        },
                    }
                ],
            }
        ),
        "utf-8",
    )

    result = await run_subagent(context, "manga_workflow_status", {"episode": 1})

    assert result["stage"] == "complete"
    assert "generate_video" not in result["next_action"]


# ---------------------------------------------------------------------------
# placeholder skills
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("skill", ["generate_storyboard", "generate_video", "compose_video"])
async def test_asset_skills_require_script_file(context: SkillCallContext, skill: str) -> None:
    """没有 scripts/episode_1.json 时，三個资产 skill 都应返回 missing_prerequisite。"""
    result = await run_subagent(context, skill, {"episode": 1})
    assert result["error"] == "missing_prerequisite"


@pytest.mark.asyncio
@pytest.mark.parametrize("skill", ["generate_storyboard", "generate_video", "compose_video"])
async def test_asset_skills_reject_invalid_episode(context: SkillCallContext, skill: str) -> None:
    result = await run_subagent(context, skill, {"episode": 0})
    assert result["error"] == "invalid_argument"


@pytest.mark.asyncio
async def test_compose_video_uses_current_python_executable(
    context: SkillCallContext,
    project_root: Path,
    project_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdir = project_root / project_name
    (pdir / "scripts").mkdir(parents=True, exist_ok=True)
    (pdir / "scripts" / "episode_1.json").write_text(
        json.dumps(
            {
                "content_mode": "narration",
                "segments": [
                    {
                        "segment_id": "E1S1",
                        "generated_assets": {"video_clip": "videos/scene_E1S1.mp4"},
                    }
                ],
            }
        ),
        "utf-8",
    )
    (pdir / "videos" / "scene_E1S1.mp4").write_bytes(b"mp4")

    captured: dict[str, Any] = {}

    def fake_run(cmd: list[str], **kwargs: Any) -> SimpleNamespace:
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)

    result = await run_subagent(context, "compose_video", {"episode": 1})

    assert result["ok"] is True
    assert captured["cmd"][0] == sys.executable
    assert captured["cmd"][4] == "episode_1_final.mp4"


@pytest.mark.asyncio
async def test_generate_storyboard_enqueues_each_segment(
    context: SkillCallContext,
    project_manager: ProjectManager,
    project_name: str,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """有劇本时 generate_storyboard 应为每個 segment 入队一個 storyboard task。"""
    # 構造假劇本（narration 模式：用 segments + segment_id + image_prompt）
    pdir = project_root / project_name
    (pdir / "scripts").mkdir(parents=True, exist_ok=True)
    (pdir / "scripts" / "episode_1.json").write_text(
        json.dumps(
            {
                "content_mode": "narration",
                "segments": [
                    {"segment_id": "1", "image_prompt": "a"},
                    {"segment_id": "2", "image_prompt": "b"},
                ],
            }
        ),
        encoding="utf-8",
    )

    # 攔截實際 queue，模擬全部成功
    captured: list[Any] = []

    async def fake_batch(
        project: str, specs: list[Any], on_success: Any, on_failure: Any
    ) -> tuple[list[Any], list[Any]]:
        captured.append((project, specs))
        from lib.generation_queue_client import BatchTaskResult

        successes = [
            BatchTaskResult(
                resource_id=s.resource_id,
                task_id=f"task-{i}",
                status="succeeded",
                result={"file_path": f"storyboards/scene_{s.resource_id}.png"},
            )
            for i, s in enumerate(specs)
        ]
        return successes, []

    monkeypatch.setattr(
        "lib.generation_queue_client._batch_enqueue_and_wait",
        fake_batch,
    )

    result = await run_subagent(context, "generate_storyboard", {"episode": 1})
    assert result["ok"] is True
    assert sorted(result["succeeded"]) == ["1", "2"]
    assert result["failed"] == []
    # 確認 batch 收到 2 個 spec
    assert len(captured) == 1
    _project, specs = captured[0]
    assert _project == project_name
    assert {s.resource_id for s in specs} == {"1", "2"}
    assert all(s.task_type == "storyboard" for s in specs)


@pytest.mark.asyncio
async def test_generate_storyboard_filters_by_scene_ids(
    context: SkillCallContext,
    project_root: Path,
    project_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdir = project_root / project_name
    (pdir / "scripts").mkdir(parents=True, exist_ok=True)
    (pdir / "scripts" / "episode_1.json").write_text(
        json.dumps(
            {
                "content_mode": "narration",
                "segments": [
                    {"segment_id": "1", "image_prompt": "a"},
                    {"segment_id": "2", "image_prompt": "b"},
                    {"segment_id": "3", "image_prompt": "c"},
                ],
            }
        ),
        encoding="utf-8",
    )

    seen_ids: list[str] = []

    async def fake_batch(
        project: str, specs: list[Any], on_success: Any, on_failure: Any
    ) -> tuple[list[Any], list[Any]]:
        seen_ids.extend(s.resource_id for s in specs)
        return [], []

    monkeypatch.setattr(
        "lib.generation_queue_client._batch_enqueue_and_wait",
        fake_batch,
    )

    await run_subagent(context, "generate_storyboard", {"episode": 1, "scene_ids": ["2"]})
    assert seen_ids == ["2"]


@pytest.mark.asyncio
async def test_generate_video_carries_scene_video_settings(
    context: SkillCallContext,
    project_root: Path,
    project_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdir = project_root / project_name
    (pdir / "scripts").mkdir(parents=True, exist_ok=True)
    (pdir / "scripts" / "episode_1.json").write_text(
        json.dumps(
            {
                "content_mode": "narration",
                "segments": [
                    {
                        "segment_id": "E1S04",
                        "video_prompt": {"action": "轉身", "camera_motion": "Static"},
                        "video_backend": "byteplus/doubao-seedance-2-0-260128",
                        "video_resolution": "480p",
                        "duration_seconds": 4,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    captured_specs: list[Any] = []

    async def fake_batch(
        project: str, specs: list[Any], on_success: Any, on_failure: Any
    ) -> tuple[list[Any], list[Any]]:
        captured_specs.extend(specs)
        return [], []

    monkeypatch.setattr(
        "lib.generation_queue_client._batch_enqueue_and_wait",
        fake_batch,
    )

    await run_subagent(context, "generate_video", {"episode": 1, "scene_ids": ["E1S04"]})

    assert len(captured_specs) == 1
    payload = captured_specs[0].payload
    assert payload["video_provider"] == "byteplus"
    assert payload["video_provider_settings"] == {"model": "doubao-seedance-2-0-260128"}
    assert payload["video_resolution"] == "480p"
    assert payload["duration_seconds"] == 4


@pytest.mark.asyncio
async def test_generate_video_uses_settings_saved_by_update_video_settings(
    context: SkillCallContext,
    project_root: Path,
    project_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdir = project_root / project_name
    (pdir / "scripts").mkdir(parents=True, exist_ok=True)
    (pdir / "scripts" / "episode_1.json").write_text(
        json.dumps(
            {
                "content_mode": "narration",
                "segments": [
                    {
                        "segment_id": "E1S04",
                        "video_prompt": {"action": "轉身", "camera_motion": "Static"},
                        "video_backend": "gemini-aistudio/veo-3.1-lite-generate-preview",
                        "video_resolution": "1080p",
                        "duration_seconds": 8,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    captured_specs: list[Any] = []

    async def fake_batch(
        project: str, specs: list[Any], on_success: Any, on_failure: Any
    ) -> tuple[list[Any], list[Any]]:
        captured_specs.extend(specs)
        return [], []

    monkeypatch.setattr(
        "lib.generation_queue_client._batch_enqueue_and_wait",
        fake_batch,
    )

    update_result = await run_subagent(
        context,
        "update_video_settings",
        {
            "scope": "scene",
            "episode": 1,
            "scene_ids": ["E1S04"],
            "backend": "byteplus/doubao-seedance-2-0-260128",
            "duration_seconds": 4,
            "resolution": "480p",
        },
    )
    assert update_result["ok"] is True

    await run_subagent(context, "generate_video", {"episode": 1, "scene_ids": ["E1S04"]})

    assert len(captured_specs) == 1
    payload = captured_specs[0].payload
    assert payload["video_provider"] == "byteplus"
    assert payload["video_provider_settings"] == {"model": "doubao-seedance-2-0-260128"}
    assert payload["video_resolution"] == "480p"
    assert payload["duration_seconds"] == 4


@pytest.mark.asyncio
async def test_update_video_settings_episode_scope_updates_all_items(
    context: SkillCallContext,
    project_root: Path,
    project_name: str,
) -> None:
    pdir = project_root / project_name
    (pdir / "scripts").mkdir(parents=True, exist_ok=True)
    (pdir / "scripts" / "episode_1.json").write_text(
        json.dumps(
            {
                "episode": 1,
                "content_mode": "narration",
                "segments": [
                    {"segment_id": "E1S01", "video_prompt": "a", "duration_seconds": 8},
                    {"segment_id": "E1S02", "video_prompt": "b", "duration_seconds": 8},
                ],
            }
        ),
        encoding="utf-8",
    )

    result = await run_subagent(
        context,
        "update_video_settings",
        {
            "scope": "episode",
            "episode": 1,
            "backend": "byteplus/doubao-seedance-2-0-260128",
            "duration_seconds": 4,
            "resolution": "480p",
        },
    )

    assert result["ok"] is True
    assert sorted(result["updated_scene_ids"]) == ["E1S01", "E1S02"]
    script = json.loads((pdir / "scripts" / "episode_1.json").read_text(encoding="utf-8"))
    for segment in script["segments"]:
        assert segment["video_backend"] == "byteplus/doubao-seedance-2-0-260128"
        assert segment["video_resolution"] == "480p"
        assert segment["duration_seconds"] == 4


@pytest.mark.asyncio
async def test_update_video_settings_project_scope_updates_project_defaults(
    context: SkillCallContext,
    project_manager: ProjectManager,
    project_name: str,
) -> None:
    result = await run_subagent(
        context,
        "update_video_settings",
        {
            "scope": "project",
            "backend": "byteplus/doubao-seedance-2-0-260128",
            "duration_seconds": 4,
            "resolution": "480p",
        },
    )

    assert result["ok"] is True
    project = project_manager.load_project(project_name)
    assert project["video_backend"] == "byteplus/doubao-seedance-2-0-260128"
    assert project["default_duration"] == 4
    assert project["video_model_settings"] == {"doubao-seedance-2-0-260128": {"resolution": "480p"}}


@pytest.mark.asyncio
async def test_update_video_settings_endpoint_id_is_stored_as_readable_seedance_model(
    context: SkillCallContext,
    project_manager: ProjectManager,
    project_name: str,
) -> None:
    result = await run_subagent(
        context,
        "update_video_settings",
        {
            "scope": "project",
            "provider": "byteplus",
            "model": "ep-20260508120826-lkcjf",
        },
    )

    assert result["ok"] is True
    project = project_manager.load_project(project_name)
    assert project["video_backend"] == "byteplus/doubao-seedance-2-0-260128"


# ---------------------------------------------------------------------------
# run_subagent dispatch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_subagent_unknown_skill(context: SkillCallContext) -> None:
    result = await run_subagent(context, "unknown_thing", {})
    assert result["error"] == "unknown_skill"
    assert "available" in result
    assert "generate_script" in result["available"]


@pytest.mark.asyncio
async def test_run_subagent_rejects_non_dict_args(context: SkillCallContext) -> None:
    bad_args: Any = "not-a-dict"
    result = await run_subagent(context, "manga_workflow_status", bad_args)
    assert result["error"] == "invalid_argument"


@pytest.mark.asyncio
async def test_run_subagent_catches_handler_exception(
    context: SkillCallContext, project_manager: ProjectManager, project_name: str
) -> None:
    # 删掉 project.json 让 manga_workflow_status 内部抛 FileNotFoundError 后被捕获
    (project_manager.get_project_path(project_name) / "project.json").unlink()
    result = await run_subagent(context, "manga_workflow_status", {})
    # 不应抛出，而是结构化错误
    assert result["error"] == "project_not_found"


# ---------------------------------------------------------------------------
# generate_scenes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_scenes_writes_to_project_json(
    context: SkillCallContext, project_manager: ProjectManager, project_name: str
) -> None:
    result = await run_subagent(
        context,
        "generate_scenes",
        {
            "scenes": [
                {"name": "客廳", "description": "主角的家"},
                {"name": "辦公室", "description": "主角工作的地方"},
            ]
        },
    )
    assert result == {"ok": True, "added": ["客廳", "辦公室"], "skipped": []}

    project = project_manager.load_project(project_name)
    assert "客廳" in project["scenes"]
    assert project["scenes"]["客廳"]["description"] == "主角的家"
    assert "辦公室" in project["scenes"]
    assert project["scenes"]["辦公室"]["description"] == "主角工作的地方"


@pytest.mark.asyncio
async def test_generate_scenes_rejects_missing_fields(context: SkillCallContext) -> None:
    result = await run_subagent(
        context,
        "generate_scenes",
        {
            "scenes": [
                {"name": "客廳"},  # 缺 description
                {"description": "主角的家"},  # 缺 name
            ]
        },
    )
    assert result["error"] == "nothing_added"
    assert len(result["skipped"]) == 2


# ---------------------------------------------------------------------------
# update_character / update_clue / update_scene
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_character_success(
    context: SkillCallContext, project_manager: ProjectManager, project_name: str
) -> None:
    # 預先新增一個角色
    project = project_manager.load_project(project_name)
    project["characters"]["小明"] = {"description": "舊描述", "voice_style": "舊風格"}
    project_manager.save_project(project_name, project)

    result = await run_subagent(
        context,
        "update_character",
        {"name": "小明", "description": "新描述"},
    )
    assert result["ok"] is True
    assert result["entity_type"] == "character"
    assert result["name"] == "小明"
    assert result["description"] == "新描述"

    project = project_manager.load_project(project_name)
    assert project["characters"]["小明"]["description"] == "新描述"
    assert project["characters"]["小明"]["voice_style"] == "舊風格"


@pytest.mark.asyncio
async def test_update_character_rejects_missing_description(context: SkillCallContext) -> None:
    result = await run_subagent(
        context,
        "update_character",
        {"name": "小明"},
    )
    assert result["error"] == "invalid_argument"
    assert result["reason"] == "name and description are required"


@pytest.mark.asyncio
async def test_update_character_not_found(context: SkillCallContext) -> None:
    result = await run_subagent(
        context,
        "update_character",
        {"name": "不存在的角色", "description": "新描述"},
    )
    assert result["error"] == "not_found"


@pytest.mark.asyncio
async def test_update_clue_success(
    context: SkillCallContext, project_manager: ProjectManager, project_name: str
) -> None:
    # 預先新增一個線索
    project = project_manager.load_project(project_name)
    project["clues"]["神秘鑰匙"] = {"description": "舊描述", "importance": "minor"}
    project_manager.save_project(project_name, project)

    result = await run_subagent(
        context,
        "update_clue",
        {"name": "神秘鑰匙", "description": "新描述"},
    )
    assert result["ok"] is True
    assert result["entity_type"] == "clue"
    assert result["name"] == "神秘鑰匙"
    assert result["description"] == "新描述"

    project = project_manager.load_project(project_name)
    assert project["clues"]["神秘鑰匙"]["description"] == "新描述"
    assert project["clues"]["神秘鑰匙"]["importance"] == "minor"


@pytest.mark.asyncio
async def test_update_clue_rejects_missing_description(context: SkillCallContext) -> None:
    result = await run_subagent(
        context,
        "update_clue",
        {"name": "神秘鑰匙"},
    )
    assert result["error"] == "invalid_argument"
    assert result["reason"] == "name and description are required"


@pytest.mark.asyncio
async def test_update_clue_not_found(context: SkillCallContext) -> None:
    result = await run_subagent(
        context,
        "update_clue",
        {"name": "不存在的線索", "description": "新描述"},
    )
    assert result["error"] == "not_found"


@pytest.mark.asyncio
async def test_update_scene_success(
    context: SkillCallContext, project_manager: ProjectManager, project_name: str
) -> None:
    # 預先新增一個場景
    project = project_manager.load_project(project_name)
    project["scenes"] = {"客廳": {"description": "舊描述"}}
    project_manager.save_project(project_name, project)

    result = await run_subagent(
        context,
        "update_scene",
        {"name": "客廳", "description": "新描述"},
    )
    assert result["ok"] is True
    assert result["entity_type"] == "scene"
    assert result["name"] == "客廳"
    assert result["description"] == "新描述"

    project = project_manager.load_project(project_name)
    assert project["scenes"]["客廳"]["description"] == "新描述"


@pytest.mark.asyncio
async def test_update_scene_rejects_missing_description(context: SkillCallContext) -> None:
    result = await run_subagent(
        context,
        "update_scene",
        {"name": "客廳"},
    )
    assert result["error"] == "invalid_argument"
    assert result["reason"] == "name and description are required"


@pytest.mark.asyncio
async def test_update_scene_not_found(context: SkillCallContext) -> None:
    result = await run_subagent(
        context,
        "update_scene",
        {"name": "不存在的場景", "description": "新描述"},
    )
    assert result["error"] == "not_found"


# ---------------------------------------------------------------------------
# rename_entity / delete_entity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rename_entity_success(
    context: SkillCallContext, project_manager: ProjectManager, project_name: str
) -> None:
    # 預先新增一個角色
    project = project_manager.load_project(project_name)
    project["characters"]["小明"] = {"description": "描述"}
    project_manager.save_project(project_name, project)

    result = await run_subagent(
        context,
        "rename_entity",
        {"entity_type": "character", "old_name": "小明", "new_name": "阿明"},
    )
    assert result["ok"] is True
    assert result["old_name"] == "小明"
    assert result["new_name"] == "阿明"

    project = project_manager.load_project(project_name)
    assert "小明" not in project["characters"]
    assert "阿明" in project["characters"]
    assert project["characters"]["阿明"]["description"] == "描述"


@pytest.mark.asyncio
async def test_rename_entity_not_found(context: SkillCallContext) -> None:
    result = await run_subagent(
        context,
        "rename_entity",
        {"entity_type": "character", "old_name": "不存在的角色", "new_name": "新名稱"},
    )
    assert result["error"] == "not_found"


@pytest.mark.asyncio
async def test_rename_entity_rejects_missing_names(context: SkillCallContext) -> None:
    result = await run_subagent(
        context,
        "rename_entity",
        {"entity_type": "character", "old_name": "", "new_name": "新名稱"},
    )
    assert result["error"] == "invalid_argument"
    assert result["reason"] == "old_name and new_name are required"


@pytest.mark.asyncio
async def test_delete_entity_success(
    context: SkillCallContext, project_manager: ProjectManager, project_name: str
) -> None:
    # 預先新增一個角色
    project = project_manager.load_project(project_name)
    project["characters"]["小明"] = {"description": "描述"}
    project_manager.save_project(project_name, project)

    result = await run_subagent(
        context,
        "delete_entity",
        {"entity_type": "character", "name": "小明"},
    )
    assert result["ok"] is True
    assert result["name"] == "小明"

    project = project_manager.load_project(project_name)
    assert "小明" not in project["characters"]


@pytest.mark.asyncio
async def test_delete_entity_not_found(context: SkillCallContext) -> None:
    result = await run_subagent(
        context,
        "delete_entity",
        {"entity_type": "character", "name": "不存在的角色"},
    )
    assert result["error"] == "not_found"


@pytest.mark.asyncio
async def test_delete_entity_rejects_missing_name(context: SkillCallContext) -> None:
    result = await run_subagent(
        context,
        "delete_entity",
        {"entity_type": "scene", "name": ""},
    )
    assert result["error"] == "invalid_argument"
    assert result["reason"] == "name is required"
