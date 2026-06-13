"""
環境初始化模組

載入 .env 檔案。
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def init_environment():
    """
    初始化專案環境

    1. 定位專案根目錄
    2. 載入 .env 檔案
    """
    # 獲取專案根目錄（lib 的父目錄）
    lib_dir = Path(__file__).parent
    project_root = lib_dir.parent

    # 載入 .env 檔案
    try:
        from dotenv import load_dotenv

        env_path = project_root / ".env"
        if env_path.exists():
            load_dotenv(env_path)
        else:
            load_dotenv()
    except ImportError:
        pass  # python-dotenv 未安裝時跳過

    return project_root


# 模組匯入時自動初始化
PROJECT_ROOT = init_environment()
