import pytest


def _make_ctx(tmp_path, content_mode="narration"):
    from lib.project_manager import ProjectManager
    from server.agent_runtime.skill_function_declarations import SkillCallContext
    from server.agent_runtime.tool_sandbox import ToolSandbox

    project_root = tmp_path / "projects"
    pm = ProjectManager(projects_root=project_root)
    pm.create_project("demo")
    pm.create_project_metadata("demo", title="t", style="anime", content_mode=content_mode)
    sandbox = ToolSandbox(project_root=project_root, project_name="demo")
    return (
        SkillCallContext(
            project_name="demo",
            sandbox=sandbox,
            project_manager=pm,
            session_id="gemini-full:test",
        ),
        pm,
        pm.get_project_path("demo"),
    )


def test_run_preprocess_unknown_content_mode_raises(tmp_path):
    from lib.episode_preprocess import run_preprocess
    from lib.project_manager import ProjectManager

    pm = ProjectManager(projects_root=tmp_path / "projects")
    pm.create_project("demo")
    pm.create_project_metadata("demo", title="t", style="anime", content_mode="narration")

    project = pm.load_project("demo")
    project["content_mode"] = "weird"
    pm.save_project("demo", project)

    with pytest.raises(ValueError, match="content_mode"):
        run_preprocess(pm.get_project_path("demo"), episode=1)


def test_run_preprocess_episode_without_split_raises_source_not_ready(tmp_path):
    """如果 source/ 內沒有任何原文，均分也無法執行 → 拋出 SourceNotReadyError。"""
    from lib import PROJECT_ROOT
    from lib.episode_preprocess import SourceNotReadyError, run_preprocess
    from lib.project_manager import ProjectManager

    pm = ProjectManager(projects_root=tmp_path / "projects")
    pm.create_project("demo")
    pm.create_project_metadata("demo", title="t", style="anime", content_mode="narration")
    project_path = pm.get_project_path("demo")
    # source/ 下沒有任何原文檔，無法進行均分
    (project_path / "source").mkdir(parents=True, exist_ok=True)

    with pytest.raises(SourceNotReadyError):
        run_preprocess(project_path, episode=2, content_mode="narration", repo_root=PROJECT_ROOT)


def test_handle_peek_split_point_success(tmp_path):
    import asyncio

    from server.agent_runtime.skill_function_declarations import _handle_peek_split_point

    ctx, _pm, project_dir = _make_ctx(tmp_path)
    (project_dir / "source" / "n.txt").write_text("甲" * 30 + "。" + "乙" * 30, encoding="utf-8")

    res = asyncio.run(_handle_peek_split_point(ctx, {"source": "source/n.txt", "target_chars": 20}))

    assert res.get("total_chars") == 61
    assert "nearby_breakpoints" in res


def test_handle_peek_split_point_missing_source(tmp_path):
    import asyncio

    from server.agent_runtime.skill_function_declarations import _handle_peek_split_point

    ctx, _pm, _project_dir = _make_ctx(tmp_path)

    res = asyncio.run(_handle_peek_split_point(ctx, {"source": "source/nope.txt", "target_chars": 5}))

    assert res.get("ok") is False
    assert res.get("error") == "not_found"


def test_handle_peek_split_point_path_escape(tmp_path):
    import asyncio

    from server.agent_runtime.skill_function_declarations import _handle_peek_split_point

    ctx, _pm, _project_dir = _make_ctx(tmp_path)

    res = asyncio.run(_handle_peek_split_point(ctx, {"source": "../../etc/passwd", "target_chars": 5}))

    assert res.get("ok") is False
    assert res.get("error") == "path_escape"


def test_handle_split_episode_success_and_persisted(tmp_path):
    import asyncio

    from server.agent_runtime.skill_function_declarations import _handle_split_episode

    ctx, pm, project_dir = _make_ctx(tmp_path)
    (project_dir / "source" / "n.txt").write_text("前半段。他離開了。後半段。", encoding="utf-8")

    res = asyncio.run(
        _handle_split_episode(
            ctx,
            {"source": "source/n.txt", "episode": 1, "target_chars": 5, "anchor": "他離開了。"},
        )
    )

    assert res.get("ok") is True
    assert res.get("episode") == 1
    assert any(ep["episode"] == 1 for ep in pm.load_project("demo").get("episodes", []))
    assert (project_dir / "source" / "episode_1.txt").exists()


def test_handle_split_episode_anchor_not_found(tmp_path):
    import asyncio

    from server.agent_runtime.skill_function_declarations import _handle_split_episode

    ctx, _pm, project_dir = _make_ctx(tmp_path)
    (project_dir / "source" / "n.txt").write_text("一些內容。", encoding="utf-8")

    res = asyncio.run(
        _handle_split_episode(
            ctx,
            {"source": "source/n.txt", "episode": 1, "target_chars": 2, "anchor": "不存在"},
        )
    )

    assert res.get("ok") is False


def test_handle_preprocess_episode_unknown_mode(tmp_path):
    import asyncio

    from server.agent_runtime.skill_function_declarations import _handle_preprocess_episode

    ctx, pm, _project_dir = _make_ctx(tmp_path)
    project = pm.load_project("demo")
    project["content_mode"] = "weird"
    pm.save_project("demo", project)

    res = asyncio.run(_handle_preprocess_episode(ctx, {"episode": 1}))

    assert res.get("ok") is False
    assert res.get("error") == "invalid_content_mode"


def _setup_preprocess_project(tmp_path):
    """共用 fixture：建立 demo 專案 + 預先寫好 step1 輸出檔，讓 run_preprocess 能完成檢查。"""
    from lib.project_manager import ProjectManager

    pm = ProjectManager(projects_root=tmp_path / "projects")
    pm.create_project("demo")
    pm.create_project_metadata("demo", title="t", style="anime", content_mode="narration")
    project_path = pm.get_project_path("demo")
    output_dir = project_path / "drafts" / "episode_1"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "step1_segments.md").write_text("stub", encoding="utf-8")
    return project_path


def test_run_preprocess_without_refs_no_filter_flags(tmp_path, monkeypatch):
    """不傳 refs 時，CLI 不應含任何新增旗標（向後相容）。"""
    import subprocess

    from lib import PROJECT_ROOT
    from lib.episode_preprocess import run_preprocess

    project_path = _setup_preprocess_project(tmp_path)
    captured_args: list[str] = []

    def mock_run(args, **kwargs):
        captured_args.extend(args)
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", mock_run)

    run_preprocess(project_path, episode=1, content_mode="narration", repo_root=PROJECT_ROOT)

    assert "--no-overview" not in captured_args
    assert "--no-style" not in captured_args
    assert "--characters-only" not in captured_args
    assert "--clues-only" not in captured_args
    assert "--scenes-only" not in captured_args


def test_run_preprocess_with_refs_translates_to_cli_flags(tmp_path, monkeypatch):
    """refs dict 應準確翻譯成對應 CLI 旗標。"""
    import subprocess

    from lib import PROJECT_ROOT
    from lib.episode_preprocess import run_preprocess

    project_path = _setup_preprocess_project(tmp_path)
    captured_args: list[str] = []

    def mock_run(args, **kwargs):
        captured_args.extend(args)
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", mock_run)

    run_preprocess(
        project_path,
        episode=1,
        content_mode="narration",
        repo_root=PROJECT_ROOT,
        refs={
            "overview": False,
            "style": True,
            "characters": ["拉拉布", "赫爾曼"],
            "clues": [],  # 空陣列 → 旗標仍出現但值為空字串（「都不帶」）
            "scenes": None,  # None → 不出現旗標（「全帶」）
        },
    )

    assert "--no-overview" in captured_args
    assert "--no-style" not in captured_args
    # characters：值用 ASCII Unit Separator (U+001F) 分隔,避免名字含逗號被誤拆。
    idx = captured_args.index("--characters-only")
    assert captured_args[idx + 1] == "拉拉布\x1f赫爾曼"
    # clues：空陣列 → 旗標出現，值為空字串
    idx = captured_args.index("--clues-only")
    assert captured_args[idx + 1] == ""
    # scenes：None → 完全不出現
    assert "--scenes-only" not in captured_args


def test_run_preprocess_with_explicit_source(tmp_path, monkeypatch):
    import subprocess

    from lib import PROJECT_ROOT
    from lib.episode_preprocess import run_preprocess
    from lib.project_manager import ProjectManager

    pm = ProjectManager(projects_root=tmp_path / "projects")
    pm.create_project("demo")
    pm.create_project_metadata("demo", title="t", style="anime", content_mode="narration")
    project_path = pm.get_project_path("demo")

    # 模擬建立預處理輸出檔案，因為 run_preprocess 會檢查 step1_path 檔案是否存在
    output_dir = project_path / "drafts" / "episode_1"
    output_dir.mkdir(parents=True, exist_ok=True)
    step1_file = output_dir / "step1_segments.md"
    step1_file.write_text("這是自訂來源內容", encoding="utf-8")

    captured_args = []

    def mock_run(args, **kwargs):
        captured_args.extend(args)
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", mock_run)

    # 執行預處理，傳入 source
    res = run_preprocess(
        project_path,
        episode=1,
        content_mode="narration",
        repo_root=PROJECT_ROOT,
        source="source/custom_source.txt",
    )

    assert res.get("content_mode") == "narration"
    assert res.get("step1_path") == "drafts/episode_1/step1_segments.md"
    assert "--source" in captured_args
    assert "source/custom_source.txt" in captured_args


def test_handle_preprocess_episode_with_source(tmp_path, monkeypatch):
    import asyncio

    import lib.episode_preprocess as ep
    from server.agent_runtime.skill_function_declarations import _handle_preprocess_episode

    ctx, pm, _project_dir = _make_ctx(tmp_path)

    captured_kwargs = {}

    def _mock_preprocess(*args, **kwargs):
        captured_kwargs.update(kwargs)
        return {"step1_path": "drafts/episode_1/step1_segments.md", "content_mode": "narration"}

    monkeypatch.setattr(ep, "run_preprocess", _mock_preprocess)

    res = asyncio.run(_handle_preprocess_episode(ctx, {"episode": 1, "source": "source/custom.txt"}))

    assert res.get("ok") is True
    assert res.get("step1_path") == "drafts/episode_1/step1_segments.md"
    assert captured_kwargs.get("source") == "source/custom.txt"


def test_explicit_source_json_validation_fails(tmp_path):
    import sys
    from pathlib import Path

    import pytest

    scripts_dir = (
        Path(__file__).resolve().parents[1]
        / "agent_runtime_profile"
        / ".claude"
        / "skills"
        / "generate-script"
        / "scripts"
    )
    sys.path.insert(0, str(scripts_dir))

    try:
        import normalize_drama_script
        import split_narration_segments

        project_path = tmp_path / "project"
        source_dir = project_path / "source"
        source_dir.mkdir(parents=True)

        json_file = source_dir / "invalid.json"
        json_file.write_text("{}", encoding="utf-8")

        with pytest.raises(ValueError, match="不支援的原始檔格式"):
            split_narration_segments._read_explicit_sources(project_path, "source/invalid.json")

        with pytest.raises(ValueError, match="不支援的原始檔格式"):
            normalize_drama_script._read_explicit_sources(project_path, "source/invalid.json")
    finally:
        if str(scripts_dir) in sys.path:
            sys.path.remove(str(scripts_dir))
