"""
資料驗證工具

驗證 project.json 和 episode JSON 的資料結構完整性和引用一致性。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ValidationResult:
    """驗證結果"""

    valid: bool
    errors: list[str] = field(default_factory=list)  # 錯誤列表（阻止繼續）
    warnings: list[str] = field(default_factory=list)  # 警告列表（僅提示）

    def __str__(self) -> str:
        if self.valid:
            msg = "驗證透過"
            if self.warnings:
                msg += f"\n警告 ({len(self.warnings)}):\n" + "\n".join(f"  - {warning}" for warning in self.warnings)
            return msg

        msg = f"驗證失敗 ({len(self.errors)} 個錯誤)"
        msg += "\n錯誤:\n" + "\n".join(f"  - {error}" for error in self.errors)
        if self.warnings:
            msg += f"\n警告 ({len(self.warnings)}):\n" + "\n".join(f"  - {warning}" for warning in self.warnings)
        return msg


class DataValidator:
    """資料驗證器"""

    VALID_CONTENT_MODES = {"narration", "drama"}
    VALID_DURATIONS = {4, 6, 8}
    VALID_CLUE_IMPORTANCE = {"major", "minor"}
    VALID_SCENE_TYPES = {"劇情", "空鏡"}
    ID_PATTERN = re.compile(r"^E\d+S\d+(?:_\d+)?$")
    EXTERNAL_URI_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")
    ALLOWED_ROOT_ENTRIES = {
        "project.json",
        "style_reference.png",
        "style_reference.jpg",
        "style_reference.jpeg",
        "style_reference.webp",
        "source",
        "scripts",
        "drafts",
        "characters",
        "clues",
        "scenes",
        "storyboards",
        "videos",
        "thumbnails",
        "output",
        "versions",
    }

    def __init__(self, projects_root: str | None = None):
        """
        初始化驗證器

        Args:
            projects_root: 專案根目錄，預設為 projects/
        """
        import os

        if projects_root is None:
            projects_root = os.environ.get("AI_ANIME_PROJECTS", "projects")
        self.projects_root = Path(projects_root)

    def _load_json(self, file_path: Path) -> dict[str, Any] | None:
        """載入 JSON 檔案"""
        try:
            with open(file_path, encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None

    @staticmethod
    def _is_hidden_path(path: Path) -> bool:
        return any(part.startswith(".") or part == "__MACOSX" for part in path.parts)

    def _resolve_existing_path(
        self,
        project_dir: Path,
        raw_path: str,
        *,
        default_dir: str | None = None,
    ) -> tuple[str | None, str | None]:
        normalized = str(raw_path).strip().replace("\\", "/")
        if not normalized:
            return None, "路徑不能為空"

        candidate_paths = [Path(normalized)]
        if default_dir and len(candidate_paths[0].parts) == 1:
            candidate_paths.append(Path(default_dir) / candidate_paths[0])

        project_root = project_dir.resolve()
        seen: set[str] = set()
        for candidate in candidate_paths:
            candidate_key = candidate.as_posix()
            if candidate_key in seen:
                continue
            seen.add(candidate_key)

            try:
                resolved = (project_dir / candidate).resolve(strict=False)
                resolved.relative_to(project_root)
            except ValueError:
                return None, f"引用路徑越界: {normalized}"

            if resolved.exists():
                return candidate.as_posix(), None

        return None, f"引用的檔案不存在: {normalized}"

    def _validate_local_reference(
        self,
        project_dir: Path,
        value: Any,
        errors: list[str],
        field_name: str,
        *,
        default_dir: str | None = None,
        allow_external: bool = False,
    ) -> str | None:
        if value in (None, ""):
            return None
        if not isinstance(value, str):
            errors.append(f"{field_name} 必須是字串")
            return None

        raw_value = value.strip()
        if not raw_value:
            return None

        if self.EXTERNAL_URI_PATTERN.match(raw_value):
            if allow_external:
                return raw_value
            errors.append(f"{field_name} 必須是專案內相對路徑: {raw_value}")
            return None

        resolved_path, error = self._resolve_existing_path(
            project_dir,
            raw_value,
            default_dir=default_dir,
        )
        if error:
            errors.append(f"{field_name}: {error}")
        return resolved_path

    def _validate_project_payload(
        self,
        project: dict[str, Any],
        errors: list[str],
        warnings: list[str],
    ) -> None:
        if not project.get("title"):
            errors.append("缺少必填欄位: title")

        content_mode = project.get("content_mode")
        if not content_mode:
            errors.append("缺少必填欄位: content_mode")
        elif content_mode not in self.VALID_CONTENT_MODES:
            errors.append(f"content_mode 值無效: '{content_mode}'，必須是 {self.VALID_CONTENT_MODES}")

        if not project.get("style"):
            errors.append("缺少必填欄位: style")

        episodes = project.get("episodes", [])
        if not isinstance(episodes, list):
            errors.append("episodes 必須是陣列")
        else:
            for index, episode in enumerate(episodes):
                prefix = f"episodes[{index}]"
                if not isinstance(episode, dict):
                    errors.append(f"{prefix}: 資料格式錯誤，應為物件")
                    continue

                if not isinstance(episode.get("episode"), int):
                    errors.append(f"{prefix}: 缺少必填欄位 episode (整數)")
                if not episode.get("title"):
                    errors.append(f"{prefix}: 缺少必填欄位 title")

                script_file = episode.get("script_file")
                if not script_file:
                    errors.append(f"{prefix}: 缺少必填欄位 script_file")
                elif not isinstance(script_file, str):
                    errors.append(f"{prefix}: script_file 必須是字串")

        characters = project.get("characters", {})
        if isinstance(characters, dict):
            for char_name, char_data in characters.items():
                if not isinstance(char_data, dict):
                    errors.append(f"角色 '{char_name}' 資料格式錯誤，應為物件")
                    continue

        clues = project.get("clues", {})
        if isinstance(clues, dict):
            for clue_name, clue_data in clues.items():
                if not isinstance(clue_data, dict):
                    errors.append(f"線索 '{clue_name}' 資料格式錯誤，應為物件")
                    continue

                importance = clue_data.get("importance")
                if not importance:
                    errors.append(f"線索 '{clue_name}' 缺少必填欄位: importance")
                elif importance not in self.VALID_CLUE_IMPORTANCE:
                    errors.append(
                        f"線索 '{clue_name}' importance 值無效: '{importance}'，必須是 {self.VALID_CLUE_IMPORTANCE}"
                    )

    def validate_project(self, project_name: str) -> ValidationResult:
        """驗證 project.json"""
        return self.validate_project_dir(self.projects_root / project_name)

    def validate_project_dir(self, project_dir: Path) -> ValidationResult:
        """驗證指定目錄中的 project.json。"""
        errors: list[str] = []
        warnings: list[str] = []

        project_path = Path(project_dir) / "project.json"
        project = self._load_json(project_path)
        if project is None:
            return ValidationResult(
                valid=False,
                errors=[f"無法載入 project.json: {project_path}"],
            )

        self._validate_project_payload(project, errors, warnings)
        return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)

    def _validate_generated_assets(
        self,
        project_dir: Path,
        prefix: str,
        assets: Any,
        errors: list[str],
    ) -> None:
        if assets in (None, ""):
            return
        if not isinstance(assets, dict):
            errors.append(f"{prefix}.generated_assets 必須是物件")
            return

        self._validate_local_reference(
            project_dir,
            assets.get("storyboard_image"),
            errors,
            f"{prefix}.generated_assets.storyboard_image",
            default_dir="storyboards",
        )
        self._validate_local_reference(
            project_dir,
            assets.get("video_clip"),
            errors,
            f"{prefix}.generated_assets.video_clip",
            default_dir="videos",
        )
        self._validate_local_reference(
            project_dir,
            assets.get("video_uri"),
            errors,
            f"{prefix}.generated_assets.video_uri",
            default_dir="videos",
            allow_external=True,
        )

    def _validate_segments(
        self,
        segments: list[dict[str, Any]],
        project_characters: set[str],
        project_clues: set[str],
        errors: list[str],
        warnings: list[str],
        *,
        project_dir: Path | None = None,
    ) -> None:
        """驗證 segments（narration 模式）"""
        if not segments:
            errors.append("segments 陣列為空")
            return

        for index, segment in enumerate(segments):
            prefix = f"segments[{index}]"

            segment_id = segment.get("segment_id")
            if not segment_id:
                errors.append(f"{prefix}: 缺少必填欄位 segment_id")
            elif not self.ID_PATTERN.match(segment_id):
                errors.append(f"{prefix}: segment_id 格式錯誤 '{segment_id}'，應為 E{{n}}S{{nn}}")

            duration = segment.get("duration_seconds")
            if duration is None:
                warnings.append(f"{prefix}: 缺少 duration_seconds，將使用預設值 4")
            elif duration not in self.VALID_DURATIONS:
                errors.append(f"{prefix}: duration_seconds 值無效 '{duration}'，必須是 {self.VALID_DURATIONS}")

            if not segment.get("novel_text"):
                errors.append(f"{prefix}: 缺少必填欄位 novel_text")

            chars_in_segment = segment.get("characters_in_segment")
            if chars_in_segment is None:
                errors.append(f"{prefix}: 缺少必填欄位 characters_in_segment")
            elif not isinstance(chars_in_segment, list):
                errors.append(f"{prefix}: characters_in_segment 必須是陣列")
            else:
                invalid = set(chars_in_segment) - project_characters
                if invalid:
                    errors.append(f"{prefix}: characters_in_segment 引用了不存在於 project.json 的角色: {invalid}")

            clues_in_segment = segment.get("clues_in_segment")
            if clues_in_segment is None:
                warnings.append(f"{prefix}: 缺少 clues_in_segment，將使用預設空陣列")
            elif not isinstance(clues_in_segment, list):
                errors.append(f"{prefix}: clues_in_segment 必須是陣列")
            else:
                invalid = set(clues_in_segment) - project_clues
                if invalid:
                    errors.append(f"{prefix}: clues_in_segment 引用了不存在於 project.json 的線索: {invalid}")

            if not segment.get("image_prompt"):
                errors.append(f"{prefix}: 缺少必填欄位 image_prompt")
            if not segment.get("video_prompt"):
                errors.append(f"{prefix}: 缺少必填欄位 video_prompt")

            if project_dir is not None:
                self._validate_generated_assets(
                    project_dir,
                    prefix,
                    segment.get("generated_assets"),
                    errors,
                )
                self._validate_local_reference(
                    project_dir,
                    segment.get("reference_image"),
                    errors,
                    f"{prefix}.reference_image",
                    default_dir="storyboards/refs",
                )
                self._validate_local_reference(
                    project_dir,
                    segment.get("storyboard_sheet"),
                    errors,
                    f"{prefix}.storyboard_sheet",
                    default_dir="versions/storyboards",
                )

    def _validate_scenes(
        self,
        scenes: list[dict[str, Any]],
        project_characters: set[str],
        project_clues: set[str],
        errors: list[str],
        warnings: list[str],
        *,
        project_dir: Path | None = None,
    ) -> None:
        """驗證 scenes（drama 模式）"""
        if not scenes:
            errors.append("scenes 陣列為空")
            return

        for index, scene in enumerate(scenes):
            prefix = f"scenes[{index}]"

            scene_id = scene.get("scene_id")
            if not scene_id:
                errors.append(f"{prefix}: 缺少必填欄位 scene_id")
            elif not self.ID_PATTERN.match(scene_id):
                errors.append(f"{prefix}: scene_id 格式錯誤 '{scene_id}'，應為 E{{n}}S{{nn}}")

            scene_type = scene.get("scene_type")
            if not scene_type:
                errors.append(f"{prefix}: 缺少必填欄位 scene_type")
            elif scene_type not in self.VALID_SCENE_TYPES:
                errors.append(f"{prefix}: scene_type 值無效 '{scene_type}'，必須是 {self.VALID_SCENE_TYPES}")

            duration = scene.get("duration_seconds")
            if duration is None:
                warnings.append(f"{prefix}: 缺少 duration_seconds，將使用預設值 8")
            elif duration not in self.VALID_DURATIONS:
                errors.append(f"{prefix}: duration_seconds 值無效 '{duration}'，必須是 {self.VALID_DURATIONS}")

            chars_in_scene = scene.get("characters_in_scene")
            if chars_in_scene is None:
                errors.append(f"{prefix}: 缺少必填欄位 characters_in_scene")
            elif not isinstance(chars_in_scene, list):
                errors.append(f"{prefix}: characters_in_scene 必須是陣列")
            else:
                invalid = set(chars_in_scene) - project_characters
                if invalid:
                    errors.append(f"{prefix}: characters_in_scene 引用了不存在於 project.json 的角色: {invalid}")

            clues_in_scene = scene.get("clues_in_scene")
            if clues_in_scene is None:
                warnings.append(f"{prefix}: 缺少 clues_in_scene，將使用預設空陣列")
            elif not isinstance(clues_in_scene, list):
                errors.append(f"{prefix}: clues_in_scene 必須是陣列")
            else:
                invalid = set(clues_in_scene) - project_clues
                if invalid:
                    errors.append(f"{prefix}: clues_in_scene 引用了不存在於 project.json 的線索: {invalid}")

            if not scene.get("image_prompt"):
                errors.append(f"{prefix}: 缺少必填欄位 image_prompt")
            if not scene.get("video_prompt"):
                errors.append(f"{prefix}: 缺少必填欄位 video_prompt")

            if project_dir is not None:
                self._validate_generated_assets(
                    project_dir,
                    prefix,
                    scene.get("generated_assets"),
                    errors,
                )
                self._validate_local_reference(
                    project_dir,
                    scene.get("reference_image"),
                    errors,
                    f"{prefix}.reference_image",
                    default_dir="storyboards/refs",
                )
                self._validate_local_reference(
                    project_dir,
                    scene.get("storyboard_sheet"),
                    errors,
                    f"{prefix}.storyboard_sheet",
                    default_dir="versions/storyboards",
                )

    def _validate_episode_payload(
        self,
        project_dir: Path,
        project: dict[str, Any],
        episode: dict[str, Any],
        errors: list[str],
        warnings: list[str],
    ) -> None:
        project_characters = set(project.get("characters", {}).keys())
        project_clues = set(project.get("clues", {}).keys())

        if not isinstance(episode.get("episode"), int):
            errors.append("缺少必填欄位: episode (整數)")

        if not episode.get("title"):
            errors.append("缺少必填欄位: title")

        content_mode = episode.get(
            "content_mode",
            project.get("content_mode", "narration"),
        )

        characters_in_episode = episode.get("characters_in_episode")
        if characters_in_episode is not None:
            warnings.append("characters_in_episode 欄位已廢棄（改為讀時計算），可安全移除")

        clues_in_episode = episode.get("clues_in_episode")
        if clues_in_episode is not None:
            warnings.append("clues_in_episode 欄位已廢棄（改為讀時計算），可安全移除")

        novel = episode.get("novel")
        if novel is not None and not isinstance(novel, dict):
            errors.append("novel 欄位必須是物件")

        if content_mode == "narration":
            self._validate_segments(
                episode.get("segments", []),
                project_characters,
                project_clues,
                errors,
                warnings,
                project_dir=project_dir,
            )
        else:
            self._validate_scenes(
                episode.get("scenes", []),
                project_characters,
                project_clues,
                errors,
                warnings,
                project_dir=project_dir,
            )

    def validate_episode(self, project_name: str, episode_file: str) -> ValidationResult:
        """驗證 episode JSON"""
        return self.validate_episode_file(self.projects_root / project_name, episode_file)

    def validate_episode_file(
        self,
        project_dir: Path,
        episode_file: str | Path,
    ) -> ValidationResult:
        """驗證指定目錄中的劇本檔案。"""
        errors: list[str] = []
        warnings: list[str] = []

        project_dir = Path(project_dir)
        project_path = project_dir / "project.json"
        project = self._load_json(project_path)
        if project is None:
            return ValidationResult(
                valid=False,
                errors=[f"無法載入 project.json: {project_path}"],
            )

        resolved_episode_path, error = self._resolve_existing_path(
            project_dir,
            str(episode_file),
            default_dir="scripts",
        )
        if error or resolved_episode_path is None:
            return ValidationResult(
                valid=False,
                errors=[f"無法載入劇本檔案: {project_dir / str(episode_file)}"],
            )

        episode_path = project_dir / resolved_episode_path
        episode = self._load_json(episode_path)
        if episode is None:
            return ValidationResult(
                valid=False,
                errors=[f"無法載入劇本檔案: {episode_path}"],
            )

        self._validate_episode_payload(project_dir, project, episode, errors, warnings)
        return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)

    def validate_project_tree(self, project_dir: str | Path) -> ValidationResult:
        """
        驗證完整專案目錄。

        除 project.json / episode 結構外，還會驗證本地檔案引用和頂層附加檔案。
        """
        project_dir = Path(project_dir)
        project_result = self.validate_project_dir(project_dir)
        errors = list(project_result.errors)
        warnings = list(project_result.warnings)

        project_path = project_dir / "project.json"
        project = self._load_json(project_path)
        if project is None:
            return ValidationResult(valid=False, errors=errors, warnings=warnings)

        self._validate_local_reference(
            project_dir,
            project.get("style_image"),
            errors,
            "project.style_image",
        )

        characters = project.get("characters", {})
        if isinstance(characters, dict):
            for char_name, char_data in characters.items():
                if not isinstance(char_data, dict):
                    continue
                self._validate_local_reference(
                    project_dir,
                    char_data.get("character_sheet"),
                    errors,
                    f"characters[{char_name}].character_sheet",
                    default_dir="characters",
                )
                self._validate_local_reference(
                    project_dir,
                    char_data.get("reference_image"),
                    errors,
                    f"characters[{char_name}].reference_image",
                    default_dir="characters/refs",
                )

        clues = project.get("clues", {})
        if isinstance(clues, dict):
            for clue_name, clue_data in clues.items():
                if not isinstance(clue_data, dict):
                    continue
                self._validate_local_reference(
                    project_dir,
                    clue_data.get("clue_sheet"),
                    errors,
                    f"clues[{clue_name}].clue_sheet",
                    default_dir="clues",
                )
                self._validate_local_reference(
                    project_dir,
                    clue_data.get("reference_image"),
                    errors,
                    f"clues[{clue_name}].reference_image",
                    default_dir="clues/refs",
                )

        scenes = project.get("scenes", {})
        if isinstance(scenes, dict):
            for scene_name, scene_data in scenes.items():
                if not isinstance(scene_data, dict):
                    continue
                self._validate_local_reference(
                    project_dir,
                    scene_data.get("scene_sheet"),
                    errors,
                    f"scenes[{scene_name}].scene_sheet",
                    default_dir="scenes",
                )
                self._validate_local_reference(
                    project_dir,
                    scene_data.get("scene_ref"),
                    errors,
                    f"scenes[{scene_name}].scene_ref",
                    default_dir="scenes/refs",
                )

        episodes = project.get("episodes", [])
        if isinstance(episodes, list):
            for index, episode_meta in enumerate(episodes):
                if not isinstance(episode_meta, dict):
                    continue

                script_file = episode_meta.get("script_file")
                if not isinstance(script_file, str) or not script_file.strip():
                    continue

                resolved_path = self._validate_local_reference(
                    project_dir,
                    script_file,
                    errors,
                    f"episodes[{index}].script_file",
                    default_dir="scripts",
                )
                if not resolved_path:
                    continue

                episode = self._load_json(project_dir / resolved_path)
                if episode is None:
                    errors.append(f"無法載入劇本檔案: {project_dir / resolved_path}")
                    continue

                episode_errors: list[str] = []
                episode_warnings: list[str] = []
                self._validate_episode_payload(
                    project_dir,
                    project,
                    episode,
                    episode_errors,
                    episode_warnings,
                )
                errors.extend(episode_errors)
                warnings.extend(episode_warnings)

        if project_dir.exists():
            for child in sorted(project_dir.iterdir(), key=lambda item: item.name):
                if self._is_hidden_path(Path(child.name)):
                    continue
                if child.name not in self.ALLOWED_ROOT_ENTRIES:
                    warnings.append(f"發現未識別的附加檔案/目錄: {child.name}")

        return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)


def validate_project(
    project_name: str,
    projects_root: str | None = None,
) -> ValidationResult:
    """驗證 project.json"""
    validator = DataValidator(projects_root)
    return validator.validate_project(project_name)


def validate_episode(
    project_name: str,
    episode_file: str,
    projects_root: str | None = None,
) -> ValidationResult:
    """驗證 episode JSON"""
    validator = DataValidator(projects_root)
    return validator.validate_episode(project_name, episode_file)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("用法: python data_validator.py <project_name> [episode_file]")
        print("  驗證 project.json: python data_validator.py my_project")
        print("  驗證 episode JSON: python data_validator.py my_project episode_1.json")
        sys.exit(1)

    project_name = sys.argv[1]

    if len(sys.argv) >= 3:
        episode_file = sys.argv[2]
        result = validate_episode(project_name, episode_file)
        print(f"驗證 {project_name}/scripts/{episode_file}:")
    else:
        result = validate_project(project_name)
        print(f"驗證 {project_name}/project.json:")

    print(result)
    sys.exit(0 if result.valid else 1)
