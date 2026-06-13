#!/usr/bin/env python3
"""
Video Generator - 使用 Veo 3.1 API 生成影片分鏡

Usage:
    # 按 episode 生成（推薦）
    python generate_video.py episode_N.json --episode N

    # 斷點續傳
    python generate_video.py episode_N.json --episode N --resume

    # 單場景模式
    python generate_video.py episode_N.json --scene SCENE_ID

    # 批次模式（獨立生成每個場景）
    python generate_video.py episode_N.json --all

每個場景獨立生成影片，使用分鏡圖作為起始幀，然後使用 ffmpeg 拼接。
"""

import argparse
import json
import subprocess
import sys
import tempfile
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from lib.generation_queue_client import (
    BatchTaskResult,
    BatchTaskSpec,
    batch_enqueue_and_wait_sync,
)
from lib.generation_queue_client import (
    enqueue_and_wait_sync as enqueue_and_wait,
)
from lib.project_manager import ProjectManager
from lib.prompt_utils import is_structured_video_prompt, video_prompt_to_yaml

# ============================================================================
# Prompt 構建
# ============================================================================


def get_video_prompt(item: dict) -> str:
    """
    獲取影片生成 Prompt

    支援結構化 prompt 格式：如果 video_prompt 是 dict，則轉換為 YAML 格式。

    Args:
        item: 片段/場景字典

    Returns:
        video_prompt 字串（可能是 YAML 格式或普通字串）
    """
    prompt = item.get("video_prompt")
    if not prompt:
        item_id = item.get("segment_id") or item.get("scene_id")
        raise ValueError(f"片段/場景缺少 video_prompt 欄位: {item_id}")

    # 檢測是否為結構化格式
    if is_structured_video_prompt(prompt):
        # 轉換為 YAML 格式
        return video_prompt_to_yaml(prompt)

    # 避免將 dict 直接下傳導致型別錯誤
    if isinstance(prompt, dict):
        item_id = item.get("segment_id") or item.get("scene_id")
        raise ValueError(f"片段/場景 video_prompt 為物件但格式不符合結構化規範: {item_id}")

    if not isinstance(prompt, str):
        item_id = item.get("segment_id") or item.get("scene_id")
        raise TypeError(f"片段/場景 video_prompt 型別無效（期望 str 或 dict）: {item_id}")

    return prompt


def get_items_from_script(script: dict) -> tuple:
    """
    根據內容模式獲取場景/片段列表和相關欄位名

    Args:
        script: 劇本資料

    Returns:
        (items_list, id_field, char_field, clue_field) 元組
    """
    content_mode = script.get("content_mode", "narration")
    if content_mode == "narration" and "segments" in script:
        return (script["segments"], "segment_id", "characters_in_segment", "clues_in_segment")
    return (script.get("scenes", []), "scene_id", "characters_in_scene", "clues_in_scene")


def parse_scene_ids(scenes_arg: str) -> list:
    """解析逗號分隔的場景 ID 列表"""
    return [s.strip() for s in scenes_arg.split(",") if s.strip()]


DEFAULT_DURATIONS_FALLBACK = [4, 8]


def get_supported_durations(project: dict) -> list[int]:
    """從專案配置或 registry 獲取當前影片模型支援的時長列表。"""
    durations = project.get("_supported_durations")
    if durations and isinstance(durations, list):
        return durations
    # Resolve from registry via project's video_backend
    video_backend = project.get("video_backend")
    if video_backend and isinstance(video_backend, str) and "/" in video_backend:
        try:
            from lib.config.registry import PROVIDER_REGISTRY

            provider_id, model_id = video_backend.split("/", 1)
            provider_meta = PROVIDER_REGISTRY.get(provider_id)
            if provider_meta:
                model_info = provider_meta.models.get(model_id)
                if model_info and model_info.supported_durations:
                    return list(model_info.supported_durations)
        except ImportError:
            pass  # registry 不可用時（如獨立執行），回退到 DEFAULT_DURATIONS_FALLBACK
    return DEFAULT_DURATIONS_FALLBACK


def validate_duration(duration: int, supported_durations: list[int] | None = None) -> str:
    """
    驗證並返回有效的時長引數。

    Args:
        duration: 輸入的時長（秒）
        supported_durations: 當前影片模型支援的時長列表

    Returns:
        有效的時長字串
    """
    valid = supported_durations or DEFAULT_DURATIONS_FALLBACK
    if duration in valid:
        return str(duration)
    # 向上取整到最近的有效值
    for d in sorted(valid):
        if d >= duration:
            return str(d)
    return str(max(valid))


# ============================================================================
# Checkpoint 管理
# ============================================================================


def get_checkpoint_path(project_dir: Path, episode: int) -> Path:
    """獲取 checkpoint 檔案路徑"""
    return project_dir / "videos" / f".checkpoint_ep{episode}.json"


def load_checkpoint(project_dir: Path, episode: int) -> dict | None:
    """
    載入 checkpoint

    Returns:
        checkpoint 字典或 None
    """
    checkpoint_path = get_checkpoint_path(project_dir, episode)
    if checkpoint_path.exists():
        with open(checkpoint_path, encoding="utf-8") as f:
            return json.load(f)
    return None


def save_checkpoint(project_dir: Path, episode: int, completed_scenes: list, started_at: str):
    """儲存 checkpoint"""
    checkpoint_path = get_checkpoint_path(project_dir, episode)
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

    checkpoint = {
        "episode": episode,
        "completed_scenes": completed_scenes,
        "started_at": started_at,
        "updated_at": datetime.now().isoformat(),
    }

    with open(checkpoint_path, "w", encoding="utf-8") as f:
        json.dump(checkpoint, f, ensure_ascii=False, indent=2)


def clear_checkpoint(project_dir: Path, episode: int):
    """清除 checkpoint"""
    checkpoint_path = get_checkpoint_path(project_dir, episode)
    if checkpoint_path.exists():
        checkpoint_path.unlink()


# ============================================================================
# FFmpeg 拼接
# ============================================================================


def concatenate_videos(video_paths: list, output_path: Path) -> Path:
    """
    使用 ffmpeg 拼接多個影片片段

    Args:
        video_paths: 影片檔案路徑列表
        output_path: 輸出路徑

    Returns:
        輸出影片路徑
    """
    if len(video_paths) == 1:
        # 只有一個片段，直接複製
        import shutil

        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(video_paths[0], output_path)
        return output_path

    # 建立臨時檔案列表
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        for video_path in video_paths:
            f.write(f"file '{video_path}'\n")
        list_file = f.name

    try:
        # 使用 ffmpeg concat demuxer
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file, "-c", "copy", str(output_path)]
        subprocess.run(cmd, check=True, capture_output=True)
        print(f"✅ 影片已拼接: {output_path}")
        return output_path
    finally:
        Path(list_file).unlink()


# ============================================================================
# 批次任務構建輔助
# ============================================================================


def _build_video_specs(
    *,
    items: list,
    id_field: str,
    content_mode: str,
    script_filename: str,
    project_dir: Path,
    project: dict | None = None,
    skip_ids: list[str] | None = None,
) -> tuple[list[BatchTaskSpec], dict[str, int]]:
    """
    從場景/片段列表構建 BatchTaskSpec 和 resource_id -> order_index 對映。

    跳過缺少分鏡圖或 prompt 無效的項，並列印警告。

    Returns:
        (specs, order_map)  order_map: resource_id -> 原始 items 中的索引
    """
    _project = project or {}
    item_type = "片段" if content_mode == "narration" else "場景"
    default_duration = _project.get("default_duration") or (4 if content_mode == "narration" else 8)
    supported = get_supported_durations(_project)
    skip_set = set(skip_ids or [])

    specs: list[BatchTaskSpec] = []
    order_map: dict[str, int] = {}

    for idx, item in enumerate(items):
        item_id = item.get(id_field) or item.get("scene_id") or item.get("segment_id") or f"item_{idx}"

        if item_id in skip_set:
            continue

        storyboard_image = (item.get("generated_assets") or {}).get("storyboard_image")
        if not storyboard_image:
            print(f"⚠️  {item_type} {item_id} 沒有分鏡圖，跳過")
            continue
        storyboard_path = project_dir / storyboard_image
        if not storyboard_path.exists():
            print(f"⚠️  分鏡圖不存在: {storyboard_path}，跳過")
            continue

        try:
            prompt = get_video_prompt(item)
        except Exception as e:
            print(f"⚠️  {item_type} {item_id} 的 video_prompt 無效，跳過: {e}")
            continue

        duration = item.get("duration_seconds", default_duration)
        duration_str = validate_duration(duration, supported)

        specs.append(
            BatchTaskSpec(
                task_type="video",
                media_type="video",
                resource_id=item_id,
                payload={
                    "prompt": prompt,
                    "script_file": script_filename,
                    "duration_seconds": int(duration_str),
                },
                script_file=script_filename,
            )
        )
        order_map[item_id] = idx

    return specs, order_map


def _scan_completed_items(
    items: list,
    id_field: str,
    item_type: str,
    completed_scenes: list[str],
    videos_dir: Path,
) -> tuple[list[Path | None], list[str]]:
    """Scan items for already-completed videos; return ordered paths and done IDs."""
    ordered_paths: list[Path | None] = [None] * len(items)
    already_done: list[str] = []
    for idx, item in enumerate(items):
        item_id = item.get(id_field, item.get("scene_id", f"item_{idx}"))
        video_output = videos_dir / f"scene_{item_id}.mp4"
        if item_id in completed_scenes and video_output.exists():
            print(f"  [{idx + 1}/{len(items)}] {item_type} {item_id} ✓ 已完成")
            ordered_paths[idx] = video_output
            already_done.append(item_id)
        elif item_id in completed_scenes:
            completed_scenes.remove(item_id)
    return ordered_paths, already_done


def _submit_and_wait_with_checkpoint(
    *,
    project_name: str,
    project_dir: Path,
    specs: list[BatchTaskSpec],
    order_map: dict[str, int],
    ordered_paths: list[Path | None],
    completed_scenes: list[str],
    save_fn: Callable[[], None],
    item_type: str,
) -> list[BatchTaskResult]:
    """Submit specs via batch_enqueue_and_wait_sync with checkpoint on each success."""
    print(f"\n🚀 批次提交 {len(specs)} 個影片到生成佇列...\n")

    def on_success(br: BatchTaskResult) -> None:
        result = br.result or {}
        relative_path = result.get("file_path") or f"videos/scene_{br.resource_id}.mp4"
        output_path = project_dir / relative_path
        ordered_paths[order_map[br.resource_id]] = output_path
        completed_scenes.append(br.resource_id)
        save_fn()
        print(f"    ✅ 完成: {output_path.name}")

    def on_failure(br: BatchTaskResult) -> None:
        print(f"    ❌ {br.resource_id} 失敗: {br.error}")

    _, failures = batch_enqueue_and_wait_sync(
        project_name=project_name,
        specs=specs,
        on_success=on_success,
        on_failure=on_failure,
    )

    if failures:
        print(f"\n⚠️  {len(failures)} 個{item_type}生成失敗:")
        for f in failures:
            print(f"   - {f.resource_id}: {f.error}")
        print("    💡 使用 --resume 引數可從此處繼續")
        raise RuntimeError(f"{len(failures)} 個{item_type}生成失敗")

    return failures


# ============================================================================
# Episode 影片生成（每個場景獨立生成）
# ============================================================================


def generate_episode_video(
    script_filename: str,
    episode: int,
    resume: bool = False,
) -> list[Path]:
    """
    為指定 episode 生成所有場景的影片片段。

    每個場景獨立生成影片，使用分鏡圖作為起始幀。
    """
    pm, project_name = ProjectManager.from_cwd()
    project_dir = pm.get_project_path(project_name)
    project = pm.load_project(project_name)
    script = pm.load_script(project_name, script_filename)
    content_mode = script.get("content_mode", "narration")
    all_items, id_field, _, _ = get_items_from_script(script)

    episode_items = [s for s in all_items if s.get("episode", 1) == episode]
    if not episode_items:
        raise ValueError(f"未找到第 {episode} 集的場景/片段")

    item_type = "片段" if content_mode == "narration" else "場景"
    print(f"📋 第 {episode} 集共 {len(episode_items)} 個{item_type}")

    # Checkpoint
    completed_scenes: list[str] = []
    started_at = datetime.now().isoformat()
    if resume:
        checkpoint = load_checkpoint(project_dir, episode)
        if checkpoint:
            completed_scenes = checkpoint.get("completed_scenes", [])
            started_at = checkpoint.get("started_at", started_at)
            print(f"🔄 從 checkpoint 恢復，已完成 {len(completed_scenes)} 個場景")
        else:
            print("⚠️  未找到 checkpoint，從頭開始")

    videos_dir = project_dir / "videos"
    videos_dir.mkdir(parents=True, exist_ok=True)

    ordered_video_paths, already_done_ids = _scan_completed_items(
        episode_items,
        id_field,
        item_type,
        completed_scenes,
        videos_dir,
    )
    specs, order_map = _build_video_specs(
        items=episode_items,
        id_field=id_field,
        content_mode=content_mode,
        script_filename=script_filename,
        project_dir=project_dir,
        project=project,
        skip_ids=already_done_ids,
    )

    if not specs and not any(ordered_video_paths):
        raise RuntimeError("沒有可生成的影片片段")

    if specs:
        _submit_and_wait_with_checkpoint(
            project_name=project_name,
            project_dir=project_dir,
            specs=specs,
            order_map=order_map,
            ordered_paths=ordered_video_paths,
            completed_scenes=completed_scenes,
            save_fn=lambda: save_checkpoint(project_dir, episode, completed_scenes, started_at),
            item_type=item_type,
        )

    scene_videos = [p for p in ordered_video_paths if p is not None]
    if not scene_videos:
        raise RuntimeError("沒有生成任何影片片段")

    clear_checkpoint(project_dir, episode)
    print(f"\n🎉 第 {episode} 集影片生成完成，共 {len(scene_videos)} 個片段")
    return scene_videos


# ============================================================================
# 單場景生成
# ============================================================================


def generate_scene_video(script_filename: str, scene_id: str) -> Path:
    """
    生成單個場景/片段的影片

    Args:
        script_filename: 劇本檔名
        scene_id: 場景/片段 ID

    Returns:
        生成的影片路徑
    """
    pm, project_name = ProjectManager.from_cwd()
    project_dir = pm.get_project_path(project_name)
    project = pm.load_project(project_name)

    # 載入劇本
    script = pm.load_script(project_name, script_filename)
    content_mode = script.get("content_mode", "narration")
    all_items, id_field, _, _ = get_items_from_script(script)

    # 找到指定場景/片段
    item = None
    for s in all_items:
        if s.get(id_field) == scene_id or s.get("scene_id") == scene_id:
            item = s
            break

    if not item:
        raise ValueError(f"場景/片段 '{scene_id}' 不存在")

    # 檢查分鏡圖
    storyboard_image = item.get("generated_assets", {}).get("storyboard_image")
    if not storyboard_image:
        raise ValueError(f"場景/片段 '{scene_id}' 沒有分鏡圖，請先執行 generate-storyboard")

    storyboard_path = project_dir / storyboard_image
    if not storyboard_path.exists():
        raise FileNotFoundError(f"分鏡圖不存在: {storyboard_path}")

    # 直接使用 video_prompt 欄位
    prompt = get_video_prompt(item)

    # 獲取時長（優先專案配置，說書模式預設 4 秒，劇集動畫預設 8 秒）
    default_duration = project.get("default_duration") or (4 if content_mode == "narration" else 8)
    duration = item.get("duration_seconds", default_duration)
    supported = get_supported_durations(project)
    duration_str = validate_duration(duration, supported)

    print(f"🎬 正在生成影片: 場景/片段 {scene_id}")
    print("   預計等待時間: 1-6 分鐘")

    queued = enqueue_and_wait(
        project_name=project_name,
        task_type="video",
        media_type="video",
        resource_id=scene_id,
        payload={
            "prompt": prompt,
            "script_file": script_filename,
            "duration_seconds": int(duration_str),
        },
        script_file=script_filename,
        source="skill",
    )
    result = queued.get("result") or {}
    relative_path = result.get("file_path") or f"videos/scene_{scene_id}.mp4"
    output_path = project_dir / relative_path

    print(f"✅ 影片已儲存: {output_path}")
    return output_path


def generate_all_videos(script_filename: str) -> list:
    """
    生成所有待處理場景的影片（獨立模式）

    Returns:
        生成的影片路徑列表
    """
    pm, project_name = ProjectManager.from_cwd()
    project_dir = pm.get_project_path(project_name)
    project = pm.load_project(project_name)

    # 載入劇本
    script = pm.load_script(project_name, script_filename)
    content_mode = script.get("content_mode", "narration")
    all_items, id_field, _, _ = get_items_from_script(script)

    pending_items = [item for item in all_items if not (item.get("generated_assets") or {}).get("video_clip")]

    if not pending_items:
        print("✨ 所有場景/片段的影片都已生成")
        return []

    item_type = "片段" if content_mode == "narration" else "場景"
    print(f"📋 共 {len(pending_items)} 個{item_type}待生成影片")
    print("⚠️  每個影片可能需要 1-6 分鐘，請耐心等待")
    print("💡 推薦使用 --episode N 模式生成並自動拼接")

    specs, _ = _build_video_specs(
        items=pending_items,
        id_field=id_field,
        content_mode=content_mode,
        script_filename=script_filename,
        project_dir=project_dir,
        project=project,
    )

    if not specs:
        print("⚠️  沒有任何可生成的影片任務（可能缺少分鏡圖或 prompt）")
        return []

    print(f"\n🚀 批次提交 {len(specs)} 個影片到生成佇列...\n")

    result_paths: list[Path] = []

    def on_success(br: BatchTaskResult) -> None:
        result = br.result or {}
        relative_path = result.get("file_path") or f"videos/scene_{br.resource_id}.mp4"
        output_path = project_dir / relative_path
        result_paths.append(output_path)
        print(f"✅ 完成: {output_path.name}")

    def on_failure(br: BatchTaskResult) -> None:
        print(f"❌ {br.resource_id} 失敗: {br.error}")

    _, failures = batch_enqueue_and_wait_sync(
        project_name=project_name,
        specs=specs,
        on_success=on_success,
        on_failure=on_failure,
    )

    if failures:
        print(f"\n⚠️  {len(failures)} 個{item_type}生成失敗:")
        for f in failures:
            print(f"   - {f.resource_id}: {f.error}")

    print(f"\n🎉 批次影片生成完成，共 {len(result_paths)} 個")
    return result_paths


def generate_selected_videos(
    script_filename: str,
    scene_ids: list,
    resume: bool = False,
) -> list:
    """
    生成指定的多個場景影片

    Args:
        script_filename: 劇本檔名
        scene_ids: 場景 ID 列表
        resume: 是否從斷點續傳

    Returns:
        生成的影片路徑列表
    """
    import hashlib

    pm, project_name = ProjectManager.from_cwd()
    project_dir = pm.get_project_path(project_name)
    project = pm.load_project(project_name)
    script = pm.load_script(project_name, script_filename)
    content_mode = script.get("content_mode", "narration")
    all_items, id_field, _, _ = get_items_from_script(script)

    # 篩選指定的場景
    items_by_id = {}
    for item in all_items:
        items_by_id[item.get(id_field, "")] = item
        if "scene_id" in item:
            items_by_id[item["scene_id"]] = item

    selected_items = []
    for scene_id in scene_ids:
        if scene_id in items_by_id:
            selected_items.append(items_by_id[scene_id])
        else:
            print(f"⚠️  場景/片段 '{scene_id}' 不存在，跳過")

    if not selected_items:
        raise ValueError("沒有找到任何有效的場景/片段")

    item_type = "片段" if content_mode == "narration" else "場景"
    print(f"📋 共選擇 {len(selected_items)} 個{item_type}")

    # Checkpoint
    scenes_hash = hashlib.md5(",".join(scene_ids).encode()).hexdigest()[:8]
    checkpoint_path = project_dir / "videos" / f".checkpoint_selected_{scenes_hash}.json"
    completed_scenes: list[str] = []
    started_at = datetime.now().isoformat()

    if resume and checkpoint_path.exists():
        with open(checkpoint_path, encoding="utf-8") as f:
            checkpoint = json.load(f)
            completed_scenes = checkpoint.get("completed_scenes", [])
            started_at = checkpoint.get("started_at", started_at)
            print(f"🔄 從 checkpoint 恢復，已完成 {len(completed_scenes)} 個場景")

    videos_dir = project_dir / "videos"
    videos_dir.mkdir(parents=True, exist_ok=True)

    ordered_results, already_done_ids = _scan_completed_items(
        selected_items,
        id_field,
        item_type,
        completed_scenes,
        videos_dir,
    )
    specs, order_map = _build_video_specs(
        items=selected_items,
        id_field=id_field,
        content_mode=content_mode,
        script_filename=script_filename,
        project_dir=project_dir,
        project=project,
        skip_ids=already_done_ids,
    )

    if specs:

        def _save():
            checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            with open(checkpoint_path, "w", encoding="utf-8") as f_ckpt:
                json.dump(
                    {
                        "scene_ids": scene_ids,
                        "completed_scenes": completed_scenes,
                        "started_at": started_at,
                        "updated_at": datetime.now().isoformat(),
                    },
                    f_ckpt,
                    ensure_ascii=False,
                    indent=2,
                )

        _submit_and_wait_with_checkpoint(
            project_name=project_name,
            project_dir=project_dir,
            specs=specs,
            order_map=order_map,
            ordered_paths=ordered_results,
            completed_scenes=completed_scenes,
            save_fn=_save,
            item_type=item_type,
        )

    final_results = [p for p in ordered_results if p is not None]

    # 全部完成後清除 checkpoint
    if checkpoint_path.exists():
        checkpoint_path.unlink()

    print(f"\n🎉 批次影片生成完成，共 {len(final_results)} 個")
    return final_results


# ============================================================================
# CLI
# ============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="生成影片分鏡",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 按 episode 生成（推薦）
  python generate_video.py episode_1.json --episode 1

  # 斷點續傳
  python generate_video.py episode_1.json --episode 1 --resume

  # 單場景模式
  python generate_video.py episode_1.json --scene E1S1

  # 批次自選模式
  python generate_video.py episode_1.json --scenes E1S01,E1S05,E1S10

  # 批次模式（獨立生成）
  python generate_video.py episode_1.json --all
        """,
    )
    parser.add_argument("script", help="劇本檔名")

    # 模式選擇
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--scene", help="指定場景 ID（單場景模式）")
    mode_group.add_argument("--scenes", help="指定多個場景 ID（逗號分隔），如: E1S01,E1S05,E1S10")
    mode_group.add_argument("--all", action="store_true", help="生成所有待處理場景（獨立模式）")
    mode_group.add_argument("--episode", type=int, help="按 episode 生成並拼接（推薦）")

    # 其他選項
    parser.add_argument("--resume", action="store_true", help="從上次中斷處繼續")

    args = parser.parse_args()

    try:
        if args.scene:
            generate_scene_video(args.script, args.scene)
        elif args.scenes:
            scene_ids = parse_scene_ids(args.scenes)
            generate_selected_videos(
                args.script,
                scene_ids,
                resume=args.resume,
            )
        elif args.all:
            generate_all_videos(args.script)
        elif args.episode:
            generate_episode_video(
                args.script,
                args.episode,
                resume=args.resume,
            )
        else:
            print("請指定模式: --scene, --scenes, --all, 或 --episode")
            print("使用 --help 檢視幫助")
            sys.exit(1)

    except Exception as e:
        print(f"❌ 錯誤: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
