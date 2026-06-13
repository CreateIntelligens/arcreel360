"""一次性遷移腳本：把 project.json 內 type=="location" 的 clue 轉成 scene。

同時修正該專案 scripts/*.json 內對這些地點的引用：
從分鏡的 clues_in_segment / clues_in_scene 移除，
填入 scene_in_segment / scene_in_scene（若原為空）。

直接寫入，無 dry-run。名稱衝突時跳過並警告。

用法：
    uv run python -m scripts.migrate_location_clues_to_scenes
    uv run python -m scripts.migrate_location_clues_to_scenes <projects 目錄>
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

PROJECTS_DIR = Path(__file__).resolve().parent.parent / "projects"

# 分鏡的 clue 欄位 ↔ scene 欄位對應（narration: segment / drama: scene）
_SEGMENT_FIELDS = ("clues_in_segment", "scene_in_segment")
_SCENE_FIELDS = ("clues_in_scene", "scene_in_scene")


@dataclass
class ProjectReport:
    project: str
    migrated: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    script_warnings: list[str] = field(default_factory=list)


def _scene_entry(clue: dict) -> dict:
    """由 location clue 構建 scene 物件。"""
    return {
        "description": clue.get("description", ""),
        "scene_sheet": clue.get("clue_sheet", ""),
        "scene_ref": clue.get("reference_image", ""),
    }


def _fix_script_units(units: list, clue_field: str, scene_field: str, migrated: set[str], warnings: list[str]) -> bool:
    """修正一組分鏡（segments 或 scenes）。回傳是否有變更。"""
    changed = False
    for unit in units:
        if not isinstance(unit, dict):
            continue
        clues = unit.get(clue_field)
        if not isinstance(clues, list):
            continue
        moved = [c for c in clues if c in migrated]
        if not moved:
            continue
        remaining = [c for c in clues if c not in migrated]
        unit[clue_field] = remaining
        unit_id = unit.get("segment_id") or unit.get("scene_id") or "?"
        if not unit.get(scene_field):
            unit[scene_field] = moved[0]
            if len(moved) > 1:
                warnings.append(
                    f"分鏡 {unit_id}：原有多個地點 {moved}，已選 {moved[0]} 填入 {scene_field}，"
                    f"其餘 {moved[1:]} 請手動確認"
                )
        else:
            warnings.append(
                f"分鏡 {unit_id}：{scene_field} 已有值 '{unit[scene_field]}'，被遷移地點 {moved} 未填入，請手動確認"
            )
        changed = True
    return changed


def _fix_scripts(project_dir: Path, migrated: set[str], warnings: list[str]) -> None:
    """掃描 scripts/*.json，修正對被遷移地點的引用。"""
    scripts_dir = project_dir / "scripts"
    if not scripts_dir.is_dir():
        return
    for script_file in sorted(scripts_dir.glob("*.json")):
        try:
            data = json.loads(script_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            warnings.append(f"劇本 {script_file.name} 讀取失敗，跳過：{exc}")
            continue
        changed = False
        if isinstance(data.get("segments"), list):
            changed |= _fix_script_units(data["segments"], *_SEGMENT_FIELDS, migrated, warnings)
        if isinstance(data.get("scenes"), list):
            changed |= _fix_script_units(data["scenes"], *_SCENE_FIELDS, migrated, warnings)
        if changed:
            script_file.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def migrate_project(project_dir: Path) -> ProjectReport:
    """遷移單一專案。直接寫入 project.json 與 scripts/*.json。"""
    report = ProjectReport(project=project_dir.name)
    project_file = project_dir / "project.json"
    if not project_file.is_file():
        return report

    data = json.loads(project_file.read_text(encoding="utf-8"))
    clues = data.get("clues")
    if not isinstance(clues, dict):
        return report
    scenes = data.setdefault("scenes", {})

    location_names = [name for name, c in clues.items() if isinstance(c, dict) and c.get("type") == "location"]
    if not location_names:
        return report

    for name in location_names:
        if name in scenes:
            report.conflicts.append(name)
            continue
        scenes[name] = _scene_entry(clues[name])
        del clues[name]
        report.migrated.append(name)

    if report.migrated:
        _fix_scripts(project_dir, set(report.migrated), report.script_warnings)
        project_file.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return report


def main(argv: list[str]) -> int:
    projects_dir = Path(argv[1]).resolve() if len(argv) > 1 else PROJECTS_DIR
    if not projects_dir.is_dir():
        print(f"找不到 projects 目錄：{projects_dir}")
        return 1

    total_migrated = 0
    total_conflicts = 0
    for project_dir in sorted(p for p in projects_dir.iterdir() if p.is_dir()):
        report = migrate_project(project_dir)
        if not (report.migrated or report.conflicts or report.script_warnings):
            continue
        print(f"[{report.project}]")
        for name in report.migrated:
            print(f"  ✓ 遷移 location clue → scene：{name}")
        for name in report.conflicts:
            print(f"  ⚠ 名稱衝突，跳過（scenes 已有同名）：{name}")
        for warning in report.script_warnings:
            print(f"  ⚠ {warning}")
        total_migrated += len(report.migrated)
        total_conflicts += len(report.conflicts)

    print(f"\n完成：遷移 {total_migrated} 筆，衝突跳過 {total_conflicts} 筆。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
