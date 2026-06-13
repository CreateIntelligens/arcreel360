"""分集切分共享工具函式（re-export 自 lib.episode_splitter）。

歷史上此模組是真相源；現已收斂到 lib/episode_splitter.py，此處保留以維持
peek_split_point.py / split_episode.py 的 import 路徑不變。
"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[5]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from lib.episode_splitter import (  # noqa: E402,F401
    count_chars,
    find_anchor_near_target,
    find_char_offset,
    find_natural_breakpoints,
)
