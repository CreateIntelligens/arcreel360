from lib.version_manager import VersionManager


def test_output_versions_preserve_source_clips_and_restore_current_file(tmp_path):
    project = tmp_path / "demo"
    vm = VersionManager(project)

    current = project / "output" / "episode_1_final.mp4"
    current.parent.mkdir(parents=True, exist_ok=True)
    current.write_bytes(b"final-v1")

    assert (
        vm.add_version(
            "output",
            "1",
            "compose episode 1",
            source_file=current,
            source_clips=["videos/scene_E1S01.mp4", "videos/scene_E1S02.mp4"],
            duration_seconds=1.25,
        )
        == 1
    )

    current.write_bytes(b"final-v2")
    assert (
        vm.add_version(
            "output",
            "1",
            "compose episode 1",
            source_file=current,
            source_clips=["videos/scene_E1S03.mp4"],
            duration_seconds=2.5,
        )
        == 2
    )

    info = vm.get_versions("output", "1")
    assert info["current_version"] == 2
    assert info["versions"][0]["source_clips"] == ["videos/scene_E1S01.mp4", "videos/scene_E1S02.mp4"]
    assert info["versions"][0]["duration_seconds"] == 1.25
    assert info["versions"][1]["source_clips"] == ["videos/scene_E1S03.mp4"]
    assert info["versions"][0]["file"].startswith("versions/output/1_v1_")
    assert info["versions"][0]["file"].endswith(".mp4")

    restored = vm.restore_version("output", "1", 1, current)
    assert restored["restored_version"] == 1
    assert current.read_bytes() == b"final-v1"
