#!/usr/bin/env python3
"""
Video Composer - 使用 ffmpeg 合成最終影片

Usage:
    python compose_video.py <script_file> [--output OUTPUT] [--music MUSIC_FILE]

Example:
    python compose_video.py chapter_01_script.json --output chapter_01_final.mp4
    python compose_video.py chapter_01_script.json --music bgm.mp3
"""

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

from lib.project_manager import ProjectManager
from lib.storyboard_sequence import get_storyboard_items


def check_ffmpeg():
    """檢查 ffmpeg 是否可用"""
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False


def get_video_duration(video_path: Path) -> float:
    """獲取影片時長"""
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ],
        capture_output=True,
        text=True,
    )

    return float(result.stdout.strip())


def concatenate_simple(video_paths: list, output_path: Path):
    """
    簡單拼接（無轉場效果）

    使用 concat demuxer 進行快速拼接
    """
    # 建立臨時檔案列表
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        for path in video_paths:
            # 使用絕對路徑，避免 ffmpeg 解析相對路徑出錯
            abs_path = path.resolve()
            f.write(f"file '{abs_path}'\n")
        list_file = f.name

    try:
        cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file, "-c", "copy", str(output_path)]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg 錯誤: {result.stderr}")

    finally:
        Path(list_file).unlink()


def concatenate_with_transitions(
    video_paths: list, transitions: list, output_path: Path, transition_duration: float = 0.5
):
    """
    使用轉場效果拼接影片

    使用 xfade 濾鏡實現轉場
    """
    if len(video_paths) < 2:
        # 單個影片直接複製
        subprocess.run(["ffmpeg", "-y", "-i", str(video_paths[0]), "-c", "copy", str(output_path)])
        return

    # 構建 filter_complex
    inputs = []
    for i, path in enumerate(video_paths):
        inputs.extend(["-i", str(path)])

    # 獲取每個影片的時長
    durations = [get_video_duration(p) for p in video_paths]

    # 構建 xfade 濾鏡鏈
    filter_parts = []

    for i in range(len(video_paths) - 1):
        transition = transitions[i] if i < len(transitions) else "fade"

        # xfade 型別對映
        xfade_type = {
            "cut": None,  # 不使用轉場
            "fade": "fade",
            "dissolve": "dissolve",
            "wipe": "wipeleft",
        }.get(transition, "fade")

        if xfade_type is None:
            # cut 轉場，不需要 xfade
            continue

        if i == 0:
            prev_label = "[0:v]"
        else:
            prev_label = f"[v{i}]"

        next_label = f"[{i + 1}:v]"
        out_label = f"[v{i + 1}]" if i < len(video_paths) - 2 else "[vout]"

        # 計算偏移量
        offset = sum(durations[: i + 1]) - transition_duration * (i + 1)

        filter_parts.append(
            f"{prev_label}{next_label}xfade=transition={xfade_type}:"
            f"duration={transition_duration}:offset={offset:.3f}{out_label}"
        )

    if filter_parts:
        # 音訊也需要處理
        audio_filter = (
            ";".join([f"[{i}:a]" for i in range(len(video_paths))]) + f"concat=n={len(video_paths)}:v=0:a=1[aout]"
        )

        filter_complex = ";".join(filter_parts) + ";" + audio_filter

        cmd = [
            "ffmpeg",
            "-y",
            *inputs,
            "-filter_complex",
            filter_complex,
            "-map",
            "[vout]",
            "-map",
            "[aout]",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(output_path),
        ]
    else:
        # 全是 cut 轉場，使用簡單拼接
        concatenate_simple(video_paths, output_path)
        return

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"⚠️  轉場效果失敗，嘗試簡單拼接: {result.stderr[:200]}")
        concatenate_simple(video_paths, output_path)


def add_background_music(video_path: Path, music_path: Path, output_path: Path, music_volume: float = 0.3):
    """
    新增背景音樂

    Args:
        video_path: 影片檔案
        music_path: 音樂檔案
        output_path: 輸出檔案
        music_volume: 背景音樂音量 (0-1)
    """
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-i",
        str(music_path),
        "-filter_complex",
        f"[1:a]volume={music_volume}[bg];[0:a][bg]amix=inputs=2:duration=first[aout]",
        "-map",
        "0:v",
        "-map",
        "[aout]",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(f"新增背景音樂失敗: {result.stderr}")


def resolve_output_path(project_dir: Path, output_filename: str | None, script: dict) -> Path:
    if output_filename is None:
        novel = script.get("novel") if isinstance(script.get("novel"), dict) else {}
        chapter = str(novel.get("chapter") or "output").replace(" ", "_")
        output_filename = f"{chapter}_final.mp4"

    output_arg = Path(output_filename)
    if output_arg.is_absolute():
        return output_arg
    if output_arg.parts and output_arg.parts[0] == "output":
        return project_dir / output_arg
    return project_dir / "output" / output_arg


def compose_video(
    script_filename: str, output_filename: str = None, music_path: str = None, use_transitions: bool = True
) -> Path:
    """
    合成最終影片

    Args:
        script_filename: 劇本檔名
        output_filename: 輸出檔名
        music_path: 背景音樂檔案路徑
        use_transitions: 是否使用轉場效果

    Returns:
        輸出影片路徑
    """
    pm, project_name = ProjectManager.from_cwd()
    project_dir = pm.get_project_path(project_name)

    # 載入劇本
    script = pm.load_script(project_name, script_filename)

    # 收集影片片段
    video_paths = []
    transitions = []

    items, id_field, _, _, _ = get_storyboard_items(script)
    for item in items:
        item_id = item.get(id_field) or "<unknown>"
        video_clip = item.get("generated_assets", {}).get("video_clip")
        if not video_clip:
            raise ValueError(f"場景 {item_id} 缺少影片片段")

        video_path = project_dir / video_clip
        if not video_path.exists():
            raise FileNotFoundError(f"影片檔案不存在: {video_path}")

        video_paths.append(video_path)
        transitions.append(item.get("transition_to_next", "cut"))

    if not video_paths:
        raise ValueError("沒有可用的影片片段")

    print(f"📹 共 {len(video_paths)} 個影片片段")

    output_path = resolve_output_path(project_dir, output_filename, script)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 合成影片
    print("🎬 正在合成影片...")

    if use_transitions and any(t != "cut" for t in transitions):
        concatenate_with_transitions(video_paths, transitions, output_path)
    else:
        concatenate_simple(video_paths, output_path)

    print(f"✅ 影片合成完成: {output_path}")

    # 新增背景音樂
    if music_path:
        music_file = Path(music_path)
        if not music_file.exists():
            music_file = project_dir / music_path

        if music_file.exists():
            print("🎵 正在新增背景音樂...")
            final_output = output_path.with_stem(output_path.stem + "_with_music")
            add_background_music(output_path, music_file, final_output)
            output_path = final_output
            print(f"✅ 背景音樂新增完成: {output_path}")
        else:
            print(f"⚠️  背景音樂檔案不存在: {music_path}")

    return output_path


def main():
    parser = argparse.ArgumentParser(description="合成最終影片")
    parser.add_argument("script", help="劇本檔名")
    parser.add_argument("--output", help="輸出檔名")
    parser.add_argument("--music", help="背景音樂檔案")
    parser.add_argument("--no-transitions", action="store_true", help="不使用轉場效果")

    args = parser.parse_args()

    # 檢查 ffmpeg
    if not check_ffmpeg():
        print("❌ 錯誤: ffmpeg 未安裝或不在 PATH 中")
        print("   請安裝 ffmpeg: brew install ffmpeg (macOS)")
        sys.exit(1)

    try:
        output_path = compose_video(args.script, args.output, args.music, use_transitions=not args.no_transitions)

        print(f"\n🎉 最終影片: {output_path}")
        print("   單獨片段保留在: videos/")

    except Exception as e:
        print(f"❌ 錯誤: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
