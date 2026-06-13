from __future__ import annotations

import logging
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from lib.docx_utils import read_docx_text
from lib.project_paths import ProjectPaths
from lib.project_store import ProjectStore
from lib.source_text import read_text_with_fallback

logger = logging.getLogger(__name__)
SOURCE_FILE_SUFFIXES = {".txt", ".md", ".docx"}


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class ProjectOverview(BaseModel):
    """專案概述資料模型，用於 Gemini Structured Outputs"""

    synopsis: str = Field(description="故事梗概，200-300字，概括主線劇情")
    genre: str = Field(description="題材型別，如：古裝宮鬥、現代懸疑、玄幻修仙")
    theme: str = Field(description="核心主題，如：復仇與救贖、成長與蛻變")
    world_setting: str = Field(description="時代背景和世界觀設定，100-200字")


def _read_source_files(paths: ProjectPaths, project_name: str, max_chars: int = 50000) -> str:
    """讀取專案 source 目錄下的所有可分析原文內容"""
    try:
        project_dir = paths.get_project_path(project_name)
    except Exception as e:
        logger.error("獲取專案路徑失敗 %s: %s", project_name, e)
        return ""
    source_dir = project_dir / "source"

    if not source_dir.exists():
        return ""

    contents = []
    total_chars = 0

    # 按檔名排序，確保順序一致
    for file_path in sorted(source_dir.glob("*")):
        suffix = file_path.suffix.lower()
        if file_path.is_file() and suffix in SOURCE_FILE_SUFFIXES:
            try:
                content = read_docx_text(file_path) if suffix == ".docx" else read_text_with_fallback(file_path)
                remaining = max_chars - total_chars
                if remaining <= 0:
                    break
                if len(content) > remaining:
                    content = content[:remaining]
                contents.append(f"--- {file_path.name} ---\n{content}")
                total_chars += len(content)
            except Exception as e:
                logger.error("讀取檔案失敗 %s: %s", file_path.name, e)

    return "\n\n".join(contents)


async def generate_overview(
    store: ProjectStore,
    paths: ProjectPaths,
    project_name: str,
    *,
    model: str | None = None,
    instruction: str | None = None,
) -> dict:
    """使用 Gemini API 非同步生成專案概述"""
    from lib.text_backends.base import TextGenerationRequest, TextTaskType
    from lib.text_generator import TextGenerator

    # 讀取原始檔內容
    source_content = _read_source_files(paths, project_name)
    if not source_content:
        raise ValueError("source 目錄為空，無法生成概述")

    # 建立 TextGenerator（自動追蹤用量）
    generator = (
        await TextGenerator.create_with_model_str(model)
        if model
        else await TextGenerator.create(TextTaskType.OVERVIEW, project_name)
    )

    # 呼叫 TextGenerator（Structured Outputs）
    guidance = (instruction or "").strip()
    prompt = f"請分析以下小說內容，提取關鍵資訊：\n\n{source_content}"
    if guidance:
        prompt = f"請依照以下使用者方向生成專案概述：\n{guidance}\n\n{prompt}"

    result = await generator.generate(
        TextGenerationRequest(
            prompt=prompt,
            response_schema=ProjectOverview,
        ),
        project_name=project_name,
    )
    response_text = result.text

    # 解析並驗證響應
    overview = ProjectOverview.model_validate_json(response_text)
    overview_dict = overview.model_dump()
    overview_dict["generated_at"] = _utc_now_iso()

    # 儲存到 project.json
    project = store.load_project(project_name)
    project["overview"] = overview_dict
    store.save_project(project_name, project)

    logger.info("專案概述已生成並儲存")
    return overview_dict
