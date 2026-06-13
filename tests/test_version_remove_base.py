"""VersionManager.remove_base_version 測試。"""

from lib.version_manager import VersionManager


def _png(path, content=b"x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


class TestRemoveBaseVersion:
    def test_remove_base_only_v0(self, tmp_path):
        vm = VersionManager(tmp_path / "demo")
        src = _png(tmp_path / "up.png", b"AAA")

        # 設定 v0 基底版本
        result = vm.set_base_version("characters", "Alice", src, prompt="使用者上傳")
        v0_file_rel = result["file"]
        v0_file_abs = tmp_path / "demo" / v0_file_rel
        assert v0_file_abs.exists()

        # 驗證 entry 存在
        info = vm.get_versions("characters", "Alice")
        assert info["current_version"] == 0
        assert len(info["versions"]) == 1

        # 移除 v0
        vm.remove_base_version("characters", "Alice")

        # 驗證實體檔案已刪除
        assert not v0_file_abs.exists()

        # 驗證 entry 在 versions.json 被清空（因為沒有其他版本）
        info_after = vm.get_versions("characters", "Alice")
        assert info_after["current_version"] == 0
        assert len(info_after["versions"]) == 0

    def test_remove_base_v0_and_v1(self, tmp_path):
        vm = VersionManager(tmp_path / "demo")
        src = _png(tmp_path / "up.png", b"AAA")

        # 設定 v0 基底版本
        result = vm.set_base_version("characters", "Alice", src, prompt="使用者上傳")
        v0_file_rel = result["file"]
        v0_file_abs = tmp_path / "demo" / v0_file_rel

        # 新增 AI 版本 (v1)
        cur = _png(tmp_path / "demo" / "characters" / "Alice.png", b"AI_GEN")
        vm.add_version("characters", "Alice", "ai-1", source_file=cur)

        info = vm.get_versions("characters", "Alice")
        assert info["current_version"] == 1
        assert len(info["versions"]) == 2  # v0 and v1

        # 移除 v0
        vm.remove_base_version("characters", "Alice")

        # 驗證實體檔案已刪除
        assert not v0_file_abs.exists()

        # 驗證 v1 依然存在，且 current_version 保留為 1
        info_after = vm.get_versions("characters", "Alice")
        assert info_after["current_version"] == 1
        assert len(info_after["versions"]) == 1
        assert info_after["versions"][0]["version"] == 1

    def test_remove_base_v0_when_current_was_v0_with_v1_existing(self, tmp_path):
        vm = VersionManager(tmp_path / "demo")
        src = _png(tmp_path / "up.png", b"AAA")

        # 設定 v0 基底版本
        result = vm.set_base_version("characters", "Alice", src, prompt="使用者上傳")
        v0_file_abs = tmp_path / "demo" / result["file"]

        # 新增 AI 版本 (v1)
        cur = _png(tmp_path / "demo" / "characters" / "Alice.png", b"AI_GEN")
        vm.add_version("characters", "Alice", "ai-1", source_file=cur)

        # 恢復到 v0
        vm.restore_version("characters", "Alice", 0, cur)
        assert vm.get_current_version("characters", "Alice") == 0

        # 移除 v0
        vm.remove_base_version("characters", "Alice")

        # 驗證實體檔案已刪除
        assert not v0_file_abs.exists()

        # 驗證 current_version 重新指向 v1
        info_after = vm.get_versions("characters", "Alice")
        assert info_after["current_version"] == 1
        assert len(info_after["versions"]) == 1
        assert info_after["versions"][0]["version"] == 1
