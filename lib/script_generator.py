"""
script_generator.py - 劇本生成器

讀取 Step 1/2 的 Markdown 中間檔案，呼叫文字生成 Backend 生成最終 JSON 劇本
"""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional

from pydantic import ValidationError

from lib.config.registry import PROVIDER_REGISTRY
from lib.prompt_builders_script import (
    build_drama_prompt,
    build_narration_prompt,
)
from lib.script_models import (
    DramaEpisodeScript,
    NarrationEpisodeScript,
)
from lib.step1_draft_sync import DRAFT_MODES, apply_draft_rows_to_items, parse_draft_table
from lib.text_backends.base import TextGenerationRequest, TextTaskType
from lib.text_generator import TextGenerator

logger = logging.getLogger(__name__)


class ScriptGenerator:
    """
    劇本生成器

    讀取 Step 1/2 的 Markdown 中間檔案，呼叫 TextBackend 生成最終 JSON 劇本
    """

    def __init__(self, project_path: str | Path, generator: Optional["TextGenerator"] = None):
        """
        初始化生成器

        Args:
            project_path: 專案目錄路徑，如 projects/test0205
            generator: TextGenerator 例項（可選）。若為 None 則僅支援 build_prompt() dry-run。
        """
        self.project_path = Path(project_path)
        self.generator = generator

        # 載入 project.json
        self.project_json = self._load_project_json()
        self.content_mode = self.project_json.get("content_mode", "narration")

    @classmethod
    async def create(cls, project_path: str | Path) -> "ScriptGenerator":
        """非同步工廠方法，自動從 DB 載入供應商配置建立 TextGenerator。"""
        project_name = Path(project_path).name
        generator = await TextGenerator.create(TextTaskType.SCRIPT, project_name)
        return cls(project_path, generator)

    async def generate(
        self,
        episode: int,
        output_path: Path | None = None,
        extra_instruction: str | None = None,
    ) -> Path:
        """
        非同步生成劇集劇本

        Args:
            episode: 劇集編號
            output_path: 輸出路徑，預設為 scripts/episode_{episode}.json
            extra_instruction: 使用者於 WebUI 輸入的自由提示詞（可選），
                會包成高優先級區塊注入 prompt，不得凌駕段數/ID 等硬約束。

        Returns:
            生成的 JSON 檔案路徑
        """
        if self.generator is None:
            raise RuntimeError("TextGenerator 未初始化，請使用 ScriptGenerator.create() 工廠方法")

        # 1. 載入中間檔案
        try:
            from lib.project_manager import ProjectManager
            from lib.step1_draft_sync import sync_script_to_draft_file

            pm = ProjectManager(self.project_path.parent)
            sync_script_to_draft_file(self.project_path, episode, self.content_mode, pm)
        except Exception as e:
            logger.error("Syncing script to draft file failed: %s", e)

        step1_md = self._load_step1(episode)

        # 2. 提取角色和線索（從 project.json）
        characters = self.project_json.get("characters", {})
        clues = self.project_json.get("clues", {})

        # 3. 構建 Prompt
        if self.content_mode == "narration":
            prompt = build_narration_prompt(
                project_overview=self.project_json.get("overview", {}),
                style=self.project_json.get("style", ""),
                style_description=self.project_json.get("style_description", ""),
                characters=characters,
                clues=clues,
                segments_md=step1_md,
                supported_durations=self._resolve_supported_durations(),
                default_duration=self.project_json.get("default_duration"),
                aspect_ratio=self._resolve_aspect_ratio(),
                episode=episode,
                scenes=self.project_json.get("scenes", {}),
                extra_instruction=extra_instruction,
            )
            schema = NarrationEpisodeScript
        else:
            prompt = build_drama_prompt(
                project_overview=self.project_json.get("overview", {}),
                style=self.project_json.get("style", ""),
                style_description=self.project_json.get("style_description", ""),
                characters=characters,
                clues=clues,
                scenes_md=step1_md,
                supported_durations=self._resolve_supported_durations(),
                default_duration=self.project_json.get("default_duration"),
                aspect_ratio=self._resolve_aspect_ratio(),
                episode=episode,
                scenes=self.project_json.get("scenes", {}),
                extra_instruction=extra_instruction,
            )
            schema = DramaEpisodeScript

        # 4. 呼叫 TextBackend
        logger.info("正在生成第 %d 集劇本...", episode)
        project_name = self.project_path.name
        result = await self.generator.generate(
            TextGenerationRequest(
                prompt=prompt,
                response_schema=schema,
                max_output_tokens=32768,  # 一集約 50 段 * 600 tokens/段 + overhead
            ),
            project_name=project_name,
        )
        response_text = result.text

        # 5. 解析並驗證響應
        script_data = self._parse_response(response_text, episode)

        # 6. 補充後設資料（沿用步驟 1 已讀的 step1_md，避免重複讀檔）
        script_data = self._add_metadata(script_data, episode, step1_md=step1_md)

        # 7. 儲存檔案
        if output_path is None:
            output_path = self.project_path / "scripts" / f"episode_{episode}.json"

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(script_data, f, ensure_ascii=False, indent=2)

        logger.info("劇本已儲存至 %s", output_path)
        return output_path

    def build_prompt(self, episode: int) -> str:
        """
        構建 Prompt（用於 dry-run 模式）

        Args:
            episode: 劇集編號

        Returns:
            構建好的 Prompt 字串
        """
        try:
            from lib.project_manager import ProjectManager
            from lib.step1_draft_sync import sync_script_to_draft_file

            pm = ProjectManager(self.project_path.parent)
            sync_script_to_draft_file(self.project_path, episode, self.content_mode, pm)
        except Exception as e:
            logger.error("Syncing script to draft file failed: %s", e)

        step1_md = self._load_step1(episode)
        characters = self.project_json.get("characters", {})
        clues = self.project_json.get("clues", {})

        if self.content_mode == "narration":
            return build_narration_prompt(
                project_overview=self.project_json.get("overview", {}),
                style=self.project_json.get("style", ""),
                style_description=self.project_json.get("style_description", ""),
                characters=characters,
                clues=clues,
                segments_md=step1_md,
                supported_durations=self._resolve_supported_durations(),
                default_duration=self.project_json.get("default_duration"),
                aspect_ratio=self._resolve_aspect_ratio(),
                episode=episode,
                scenes=self.project_json.get("scenes", {}),
            )
        else:
            return build_drama_prompt(
                project_overview=self.project_json.get("overview", {}),
                style=self.project_json.get("style", ""),
                style_description=self.project_json.get("style_description", ""),
                characters=characters,
                clues=clues,
                scenes_md=step1_md,
                supported_durations=self._resolve_supported_durations(),
                default_duration=self.project_json.get("default_duration"),
                aspect_ratio=self._resolve_aspect_ratio(),
                episode=episode,
                scenes=self.project_json.get("scenes", {}),
            )

    def _resolve_supported_durations(self) -> list[int] | None:
        """從專案配置或 registry 解析當前影片模型支援的時長列表。"""
        durations = self.project_json.get("_supported_durations")
        if durations and isinstance(durations, list):
            return durations
        video_backend = self.project_json.get("video_backend")
        if video_backend and isinstance(video_backend, str) and "/" in video_backend:
            provider_id, model_id = video_backend.split("/", 1)
            provider_meta = PROVIDER_REGISTRY.get(provider_id)
            if provider_meta:
                model_info = provider_meta.models.get(model_id)
                if model_info and model_info.supported_durations:
                    return list(model_info.supported_durations)
        return None

    def _resolve_aspect_ratio(self) -> str:
        """解析專案的 aspect_ratio，向後相容。"""
        if "aspect_ratio" in self.project_json and isinstance(self.project_json["aspect_ratio"], str):
            return self.project_json["aspect_ratio"]
        return "9:16" if self.content_mode == "narration" else "16:9"

    def _load_project_json(self) -> dict:
        """載入 project.json"""
        path = self.project_path / "project.json"
        if not path.exists():
            raise FileNotFoundError(f"未找到 project.json: {path}")

        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _backfill_scene_descriptions(self, scenes: list[dict], episode: int, step1_md: str | None = None) -> None:
        """用 Step 1 表格回填各 drama 場景的 ``scene_description``（場景描述欄）與 ``narration_text``（旁白欄）。

        Step 1 是原文／配音真相源。僅在場景對應欄位尚未帶值（或為空）時回填，
        不覆蓋模型已正確產出的內容。Step 1 檔案缺失時靜默略過，不阻斷生成。
        """
        if not scenes:
            return
        if step1_md is None:
            try:
                step1_md = self._load_step1(episode)
            except FileNotFoundError:
                return
        rows = parse_draft_table(step1_md)
        if rows:
            apply_draft_rows_to_items(rows, scenes, DRAFT_MODES["drama"], only_if_empty=True)

    def _load_step1(self, episode: int) -> str:
        """載入 Step 1 的 Markdown 檔案，支援兩種檔案命名"""
        drafts_path = self.project_path / "drafts" / f"episode_{episode}"
        if self.content_mode == "narration":
            primary_path = drafts_path / "step1_segments.md"
            fallback_path = drafts_path / "step1_normalized_script.md"
        else:
            primary_path = drafts_path / "step1_normalized_script.md"
            fallback_path = drafts_path / "step1_segments.md"

        if not primary_path.exists():
            if fallback_path.exists():
                logger.warning("未找到 Step 1 檔案: %s，改用 %s", primary_path, fallback_path)
                primary_path = fallback_path
            else:
                raise FileNotFoundError(f"未找到 Step 1 檔案: {primary_path}")

        with open(primary_path, encoding="utf-8") as f:
            return f.read()

    def _parse_response(self, response_text: str, episode: int) -> dict:
        """
        解析並驗證 TextBackend 響應

        Args:
            response_text: API 返回的 JSON 文字
            episode: 劇集編號

        Returns:
            驗證後的劇本資料字典
        """
        # 清理可能的 markdown 包裝
        text = response_text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        # 解析 JSON
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON 解析失敗: {e}")

        # Pydantic 驗證
        try:
            if self.content_mode == "narration":
                validated = NarrationEpisodeScript.model_validate(data)
            else:
                validated = DramaEpisodeScript.model_validate(data)
            return validated.model_dump()
        except ValidationError as e:
            logger.warning("資料驗證警告: %s", e)
            # 返回原始資料，允許部分不符合 schema
            return data

    def _add_metadata(self, script_data: dict, episode: int, step1_md: str | None = None) -> dict:
        """
        補充劇本後設資料

        Args:
            script_data: 劇本資料
            episode: 劇集編號
            step1_md: 已讀取的 Step 1 草稿內容（供 drama 回填，避免重複讀檔）；None 時才自行讀取

        Returns:
            補充後設資料後的劇本資料
        """
        # 確保基本欄位存在
        script_data.setdefault("episode", episode)
        script_data.setdefault("content_mode", self.content_mode)

        # 新增小說資訊
        if "novel" not in script_data:
            script_data["novel"] = {
                "title": self.project_json.get("title", ""),
                "chapter": f"第{episode}集",
            }
        # 剝離已廢棄的 source_file（AI 可能虛構）
        novel = script_data.get("novel")
        if isinstance(novel, dict):
            novel.pop("source_file", None)

        # 新增時間戳
        now = datetime.now(UTC).isoformat()
        script_data.setdefault("metadata", {})
        script_data["metadata"]["created_at"] = now
        script_data["metadata"]["updated_at"] = now
        script_data["metadata"]["generator"] = self.generator.model if self.generator else "unknown"

        # 計算統計資訊 + 聚合 episode 級角色/線索（從 segment/scene 中收集）
        if self.content_mode == "narration":
            segments = script_data.get("segments", [])
            script_data["metadata"]["total_segments"] = len(segments)
            script_data["duration_seconds"] = sum(int(s.get("duration_seconds", 4)) for s in segments)
            chars_field, clues_field = "characters_in_segment", "clues_in_segment"
            items = segments
        else:
            scenes = script_data.get("scenes", [])
            script_data["metadata"]["total_scenes"] = len(scenes)
            script_data["duration_seconds"] = sum(int(s.get("duration_seconds", 8)) for s in scenes)
            chars_field, clues_field = "characters_in_scene", "clues_in_scene"
            items = scenes
            # 以 Step 1 表格的「場景描述」欄回填 scene_description（與 narration 的 novel_text 對等，
            # Step 1 為原文真相源），供分鏡／影片提示詞參考。
            self._backfill_scene_descriptions(scenes, episode, step1_md=step1_md)

        all_chars: set[str] = set()
        all_clues: set[str] = set()
        for item in items:
            for name in item.get(chars_field, []):
                if isinstance(name, str):
                    all_chars.add(name)
            for name in item.get(clues_field, []):
                if isinstance(name, str):
                    all_clues.add(name)
        script_data.pop("characters_in_episode", None)
        script_data.pop("clues_in_episode", None)

        return script_data
