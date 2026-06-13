from pathlib import Path

from lib.symlink_repair import repair_claude_symlink


def test_repair_claude_symlink_returns_stats(tmp_path: Path):
    project_dir = tmp_path / "projects" / "demo"
    project_dir.mkdir(parents=True)

    result = repair_claude_symlink(project_dir)

    assert {"created", "repaired", "skipped", "errors"} <= result.keys()
