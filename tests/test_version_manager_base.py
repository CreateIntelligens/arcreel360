"""v0 可覆蓋基底版本（set_base_version）測試。"""

from lib.version_manager import VersionManager


def _png(path, content=b"x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


class TestBaseVersion:
    def test_set_base_creates_v0_and_is_current(self, tmp_path):
        vm = VersionManager(tmp_path / "demo")
        src = _png(tmp_path / "up.png", b"AAA")

        result = vm.set_base_version("characters", "Alice", src, prompt="使用者上傳")
        assert result["version"] == 0

        info = vm.get_versions("characters", "Alice")
        assert info["current_version"] == 0
        v0 = [v for v in info["versions"] if v["version"] == 0]
        assert len(v0) == 1
        assert v0[0]["prompt"] == "使用者上傳"
        assert v0[0]["is_current"] is True

    def test_set_base_overwrites_not_accumulates(self, tmp_path):
        vm = VersionManager(tmp_path / "demo")
        vm.set_base_version("characters", "Alice", _png(tmp_path / "a.png", b"AAA"))
        vm.set_base_version("characters", "Alice", _png(tmp_path / "b.png", b"BBB"))

        info = vm.get_versions("characters", "Alice")
        v0s = [v for v in info["versions"] if v["version"] == 0]
        assert len(v0s) == 1  # 覆蓋，不累積
        # 檔案內容是最新上傳的
        v0_file = tmp_path / "demo" / v0s[0]["file"]
        assert v0_file.read_bytes() == b"BBB"

    def test_ai_versions_still_start_at_1_with_v0_present(self, tmp_path):
        vm = VersionManager(tmp_path / "demo")
        vm.set_base_version("characters", "Alice", _png(tmp_path / "base.png"))

        cur = _png(tmp_path / "demo" / "characters" / "Alice.png", b"gen1")
        assert vm.add_version("characters", "Alice", "ai-1", source_file=cur) == 1
        assert vm.add_version("characters", "Alice", "ai-2", source_file=cur) == 2

        versions = {v["version"] for v in vm.get_versions("characters", "Alice")["versions"]}
        assert versions == {0, 1, 2}

    def test_restore_v0(self, tmp_path):
        vm = VersionManager(tmp_path / "demo")
        vm.set_base_version("characters", "Alice", _png(tmp_path / "base.png", b"BASE"))
        cur = tmp_path / "demo" / "characters" / "Alice.png"
        vm.add_version("characters", "Alice", "ai-1", source_file=_png(cur, b"AI1"))

        assert vm.get_current_version("characters", "Alice") == 1
        result = vm.restore_version("characters", "Alice", 0, cur)
        assert result["current_version"] == 0
        assert cur.read_bytes() == b"BASE"

    def test_v0_url_and_prompt_accessors(self, tmp_path):
        vm = VersionManager(tmp_path / "demo")
        vm.set_base_version("characters", "Alice", _png(tmp_path / "b.png"), prompt="P0")
        assert vm.get_version_prompt("characters", "Alice", 0) == "P0"
        assert vm.get_version_file_url("characters", "Alice", 0) is not None

    def test_scenes_is_supported_resource_type(self, tmp_path):
        vm = VersionManager(tmp_path / "demo")
        vm.set_base_version("scenes", "古城", _png(tmp_path / "s.png"))
        info = vm.get_versions("scenes", "古城")
        assert info["current_version"] == 0

    def test_legacy_no_v0_unaffected(self, tmp_path):
        """既有：沒有 v0 時，AI 版本從 1 起，行為完全不變。"""
        vm = VersionManager(tmp_path / "demo")
        cur = _png(tmp_path / "demo" / "characters" / "Bob.png", b"g1")
        assert vm.add_version("characters", "Bob", "p1", source_file=cur) == 1
        assert vm.add_version("characters", "Bob", "p2", source_file=cur) == 2
        info = vm.get_versions("characters", "Bob")
        assert info["current_version"] == 2
        assert all(v["version"] >= 1 for v in info["versions"])
