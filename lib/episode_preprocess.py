"""Step 1 預處理：依 content_mode 呼叫對應的 skill 腳本。

供 HTTP 路由（server/routers/projects.py）與 gemini/openai function handler 共用。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from lib import agent_profile

_PREPROCESS_TIMEOUT = 1800

# 與 split_narration_segments.py 的 SOURCE_NOT_READY_EXIT_CODE 對齊：
# 拆段腳本以此退出碼表示「該集尚未分集切分、無法定位原文」。
_SOURCE_NOT_READY_EXIT_CODE = 3

_CONTENT_MODE_SCRIPTS = {
    "narration": ("split_narration_segments.py", "step1_segments.md"),
    "drama": ("normalize_drama_script.py", "step1_normalized_script.md"),
}
_REF_NAME_SEPARATOR = "\x1f"
_REF_FILTER_FLAGS = (
    ("characters", "--characters-only"),
    ("clues", "--clues-only"),
    ("scenes", "--scenes-only"),
)


class SourceNotReadyError(RuntimeError):
    """指定集數尚未分集切分、無法定位原文——屬使用者可修正的狀況。

    繼承 RuntimeError，讓既有把 RuntimeError 當 500 的呼叫端在未更新時
    仍能運作；已更新的 HTTP 路由則優先攔截本類別並回 400。
    """


def _append_ref_flags(cmd: list[str], refs: dict) -> None:
    """把 refs dict 翻譯成預處理腳本 CLI 旗標。"""
    if refs.get("overview") is False:
        cmd.append("--no-overview")
    if refs.get("style") is False:
        cmd.append("--no-style")

    for key, flag in _REF_FILTER_FLAGS:
        value = refs.get(key)
        if value is not None:
            cmd.extend([flag, _REF_NAME_SEPARATOR.join(value)])


def run_preprocess(
    project_path: Path,
    episode: int,
    *,
    content_mode: str | None = None,
    repo_root: Path | None = None,
    source: str | None = None,
    refs: dict | None = None,
    num_segments: int | None = None,
    model: str | None = None,
    instruction: str | None = None,
) -> dict:
    """執行某集的 Step 1 預處理。

    Args:
        refs: 細粒度參考來源控制(可省略 → 全帶,維持向後相容)。可用鍵:
            - ``overview`` (bool, 預設 True):False 代表不帶 overview 區塊。
            - ``style`` (bool, 預設 True):False 代表不帶 style 區塊。
            - ``characters`` / ``clues`` / ``scenes`` (list[str] | None):
              ``None`` 代表「全帶」(等同省略),``[]`` 代表「都不帶」,
              字串陣列代表「只帶這些名字」(不存在的名字靜默忽略)。
        num_segments: 指定生成的片段數量或場景數量。

    Returns:
        {step1_path, content_mode}

    Raises:
        ValueError: content_mode 不合法。
        FileNotFoundError: 預處理腳本不存在。
        SourceNotReadyError: 該集尚未分集切分、無法定位原文(使用者可修正)。
        RuntimeError: 腳本執行失敗或逾時。
    """
    project_path = Path(project_path)
    if content_mode is None:
        project_json = project_path / "project.json"
        content_mode = "narration"
        try:
            if project_json.exists():
                content_mode = json.loads(project_json.read_text(encoding="utf-8")).get("content_mode", "narration")
        except Exception:
            content_mode = "narration"

    if content_mode not in _CONTENT_MODE_SCRIPTS:
        raise ValueError(f"未知的 content_mode: {content_mode}")

    script_filename, output_filename = _CONTENT_MODE_SCRIPTS[content_mode]
    repo_root = Path(repo_root) if repo_root is not None else project_path.resolve().parents[1]
    skill_script = agent_profile.skills_root(repo_root) / "generate-script" / "scripts" / script_filename
    if not skill_script.exists():
        raise FileNotFoundError(f"找不到預處理腳本: {skill_script}")

    cmd = [sys.executable, str(skill_script), "--episode", str(episode)]
    if source is not None:
        cmd.extend(["--source", source])
    if num_segments is not None:
        cmd.extend(["--num-segments", str(num_segments)])
    if model:
        cmd.extend(["--model", model])
    if instruction:
        cmd.extend(["--instruction", instruction])

    if refs:
        _append_ref_flags(cmd, refs)

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(project_path),
            capture_output=True,
            text=True,
            timeout=_PREPROCESS_TIMEOUT,
        )
    except subprocess.TimeoutExpired as e:
        raise RuntimeError("預處理執行逾時（>30 分鐘）") from e

    if proc.returncode == _SOURCE_NOT_READY_EXIT_CODE:
        # 該集尚未分集切分：使用者可修正，交由路由映射成 HTTP 400。
        # 優先解析 stderr 中的 SourceNotReadyError: 乾淨訊息
        detail = ""
        stderr_content = proc.stderr or ""
        for line in stderr_content.splitlines():
            if line.startswith("SourceNotReadyError:"):
                detail = line.replace("SourceNotReadyError:", "", 1).strip()
                break
        if not detail:
            # Fallback 到 stdout/stderr，過濾 ❌ 表情符號與前後雜訊
            raw = proc.stdout.strip() or proc.stderr.strip()
            if raw.startswith("❌"):
                raw = raw[1:].strip()
            detail = raw[-2000:]
        raise SourceNotReadyError(detail or f"第 {episode} 集尚未分集切分，請先切分後再執行拆段。")
    if proc.returncode != 0:
        raise RuntimeError(f"{script_filename} 失敗 (rc={proc.returncode}): {proc.stderr[-2000:]}")

    step1_path = project_path / "drafts" / f"episode_{episode}" / output_filename
    rel = f"drafts/episode_{episode}/{output_filename}" if step1_path.exists() else ""
    return {"step1_path": rel, "content_mode": content_mode}
