# AI Anime Generator Library
# 共享 Python 庫，用於 Gemini API 封裝和專案管理

# 首先初始化環境（啟用 .venv，載入 .env）
from . import agent_profile
from .data_validator import DataValidator, ValidationResult, validate_episode, validate_project
from .env_init import PROJECT_ROOT
from .project_manager import ProjectManager

__all__ = [
    "ProjectManager",
    "PROJECT_ROOT",
    "DataValidator",
    "validate_project",
    "validate_episode",
    "ValidationResult",
    "agent_profile",
]
