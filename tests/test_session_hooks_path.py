from pathlib import Path

from server.agent_runtime.session_hooks import encode_sdk_project_path, is_path_allowed


def test_encode_sdk_project_path_is_deterministic(tmp_path: Path):
    a = encode_sdk_project_path(tmp_path / "demo")
    b = encode_sdk_project_path(tmp_path / "demo")
    assert a == b


def test_is_path_allowed_rejects_outside_root(tmp_path: Path):
    root = tmp_path / "projects"
    project_cwd = root / "demo"
    project_cwd.mkdir(parents=True)

    assert is_path_allowed(str(project_cwd / "a.txt"), "Read", project_cwd, project_root=root)[0] is True
    assert is_path_allowed("/etc/passwd", "Read", project_cwd, project_root=root)[0] is False
