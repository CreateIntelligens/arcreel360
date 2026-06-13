"""
Project agent-profile symlink repair helpers.
"""

from __future__ import annotations

import logging
from pathlib import Path

from lib import agent_profile

logger = logging.getLogger(__name__)


def repair_claude_symlink(project_dir: Path, *, profile_root: Path | None = None) -> dict:
    """修復專案目錄的 .claude 和 CLAUDE.md 軟連線。"""
    project_dir = Path(project_dir)
    if profile_root is None:
        profile_root = project_dir.parent.parent

    symlink_targets = agent_profile.project_symlink_targets(profile_root)
    relative_targets = agent_profile.project_symlink_relative_targets()

    stats = {"created": 0, "repaired": 0, "skipped": 0, "errors": 0}
    for name, target_source in symlink_targets.items():
        if not target_source.exists():
            continue
        symlink_path = project_dir / name
        if symlink_path.is_symlink() and not symlink_path.exists():
            try:
                symlink_path.unlink()
                symlink_path.symlink_to(relative_targets[name])
                stats["repaired"] += 1
            except OSError as e:
                logger.warning("無法修復專案 %s 的 %s 符號連結: %s", project_dir.name, name, e)
                stats["errors"] += 1
        elif not symlink_path.exists() and not symlink_path.is_symlink():
            try:
                symlink_path.symlink_to(relative_targets[name])
                stats["created"] += 1
            except OSError as e:
                logger.warning("無法為專案 %s 建立 %s 符號連結: %s", project_dir.name, name, e)
                stats["errors"] += 1
        else:
            stats["skipped"] += 1
    return stats


def repair_all_symlinks(projects_root: Path) -> dict:
    """掃描所有專案目錄，修復軟連線。"""
    projects_root = Path(projects_root)
    totals = {"created": 0, "repaired": 0, "skipped": 0, "errors": 0}
    if not projects_root.exists():
        return totals

    profile_root = projects_root.parent
    for project_dir in sorted(projects_root.iterdir()):
        if not project_dir.is_dir() or project_dir.name.startswith("."):
            continue
        try:
            result = repair_claude_symlink(project_dir, profile_root=profile_root)
            for key in ("created", "repaired", "skipped", "errors"):
                totals[key] += result.get(key, 0)
        except Exception as e:
            logger.warning("修復專案 %s 軟連線時出錯: %s", project_dir.name, e)
            totals["errors"] += 1
    return totals
