"""Helpers for reading episode-level generation overrides from project data."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def read_episode_override(project: dict, script_file: str | None, field: str) -> Any:
    """Read an episode override for a script file.

    Empty strings are treated as unset. Matching by basename keeps compatibility
    with callers that pass either ``scripts/episode_N.json`` or ``episode_N.json``.
    """
    if not script_file:
        return None

    target_name = Path(script_file).name
    for episode in project.get("episodes", []):
        episode_script = episode.get("script_file")
        if not episode_script or Path(episode_script).name != target_name:
            continue

        overrides = episode.get("overrides") or {}
        value = overrides.get(field)
        if value is None:
            return None
        if isinstance(value, str):
            return value if value.strip() else None
        return value

    return None
