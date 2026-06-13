import importlib.util
import json
import sys
from pathlib import Path

import pytest


def load_normalize_script():
    script_path = (
        Path(__file__).resolve().parents[2]
        / "agent_runtime_profile"
        / ".claude"
        / "skills"
        / "generate-script"
        / "scripts"
        / "normalize_drama_script.py"
    )
    spec = importlib.util.spec_from_file_location("normalize_drama_script", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["normalize_drama_script"] = module
    spec.loader.exec_module(module)
    return module


normalize_drama_script = load_normalize_script()


def test_resolve_novel_text_normal(tmp_path):
    """案例 1：當 episode_2.txt 存在時，只讀取 episode_2.txt（不混入第 1 集）。"""
    source_dir = tmp_path / "source"
    source_dir.mkdir(parents=True, exist_ok=True)

    (source_dir / "episode_1.txt").write_text("Episode 1 Content", encoding="utf-8")
    (source_dir / "episode_2.txt").write_text("Episode 2 Content", encoding="utf-8")
    (source_dir / "_remaining.txt").write_text("Remaining Content", encoding="utf-8")

    result = normalize_drama_script.resolve_novel_text(tmp_path, episode=2, source=None)
    assert result == "Episode 2 Content"


def _write_project(project_path, episodes):
    """寫一份最小 project.json，episodes 為 [{"episode": N}, ...]。"""
    (project_path / "project.json").write_text(
        json.dumps({"episodes": episodes}, ensure_ascii=False),
        encoding="utf-8",
    )


def test_resolve_novel_text_episode2_auto_split_from_whole(tmp_path):
    """drama 模式對齊 narration:缺 episode_2.txt 且未指定 source 時,按集數均分整本取本集那段,
    而不是直接回傳整本(早期行為已修正,否則多集會生成重複內容)。"""
    source_dir = tmp_path / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    whole = "甲" * 40 + "。" + "乙" * 40 + "。"
    (source_dir / "novel.md").write_text(whole, encoding="utf-8")
    _write_project(tmp_path, [{"episode": 1}, {"episode": 2}])

    ep1 = normalize_drama_script.resolve_novel_text(tmp_path, episode=1, source=None)
    ep2 = normalize_drama_script.resolve_novel_text(tmp_path, episode=2, source=None)

    # 兩段拼回等於原文(契約),且各自非整本(均分而非回整本)。
    assert ep1 + ep2 == whole
    assert ep1 != whole
    assert ep2 != whole


def test_resolve_novel_text_episode1_single_episode_uses_whole(tmp_path):
    """只有 1 集：整本即第 1 集。"""
    source_dir = tmp_path / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "novel.md").write_text("整本原文內容。", encoding="utf-8")
    _write_project(tmp_path, [{"episode": 1}])

    result = normalize_drama_script.resolve_novel_text(tmp_path, episode=1, source=None)
    assert result == "整本原文內容。"


def test_resolve_novel_text_multi_source_files_concatenated(tmp_path):
    """source/ 多檔：按檔名排序串接。"""
    source_dir = tmp_path / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "01_chapter.md").write_text("第一章內容。", encoding="utf-8")
    (source_dir / "02_chapter.md").write_text("第二章內容。", encoding="utf-8")
    _write_project(tmp_path, [{"episode": 1}])

    result = normalize_drama_script.resolve_novel_text(tmp_path, episode=1, source=None)
    assert result == "第一章內容。\n\n第二章內容。"


def test_resolve_novel_text_reads_legacy_encoded_source(tmp_path):
    """source/ 文字檔可能來自 Word/Windows，預處理需支援常見台灣 legacy 編碼。"""
    source_dir = tmp_path / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    content = "時間是 1980 年代的台灣夏天。\n街角的柑仔店。"
    (source_dir / "時間是 1980 年代的台灣夏天.txt").write_bytes(content.encode("cp950"))
    _write_project(tmp_path, [{"episode": 1}])

    result = normalize_drama_script.resolve_novel_text(tmp_path, episode=1, source=None)

    assert result == content


def test_resolve_novel_text_excludes_remaining_txt(tmp_path):
    """串接整本時排除 _remaining.txt（分集切分的產物）。"""
    source_dir = tmp_path / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "novel.md").write_text("正文內容。", encoding="utf-8")
    (source_dir / "_remaining.txt").write_text("不該被串進來", encoding="utf-8")
    _write_project(tmp_path, [{"episode": 1}])

    result = normalize_drama_script.resolve_novel_text(tmp_path, episode=1, source=None)
    assert result == "正文內容。"


def test_resolve_novel_text_empty_source_dir_raises(tmp_path):
    """source/ 完全沒有原文檔 → SourceNotReadyError。"""
    (tmp_path / "source").mkdir(parents=True, exist_ok=True)
    _write_project(tmp_path, [{"episode": 1}])

    with pytest.raises(normalize_drama_script.SourceNotReadyError):
        normalize_drama_script.resolve_novel_text(tmp_path, episode=1, source=None)


def test_resolve_novel_text_prefers_episode_file_over_autosplit(tmp_path):
    """episode_2.txt 存在時，仍優先用它。"""
    source_dir = tmp_path / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "novel.md").write_text("整本不該被用。", encoding="utf-8")
    (source_dir / "episode_2.txt").write_text("第二集專屬原文。", encoding="utf-8")
    _write_project(tmp_path, [{"episode": 1}, {"episode": 2}])

    result = normalize_drama_script.resolve_novel_text(tmp_path, episode=2, source=None)
    assert result == "第二集專屬原文。"


def test_resolve_novel_text_explicit_source_overrides_autosplit(tmp_path):
    """有指定 source 時，用指定的。"""
    source_dir = tmp_path / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "novel.md").write_text("整本不該被用。", encoding="utf-8")
    (source_dir / "我指定的.txt").write_text("使用者指定的原文。", encoding="utf-8")
    _write_project(tmp_path, [{"episode": 1}, {"episode": 2}])

    result = normalize_drama_script.resolve_novel_text(tmp_path, episode=2, source="source/我指定的.txt")
    assert result == "使用者指定的原文。"


def test_source_not_ready_error_is_filenotfound_subclass():
    """SourceNotReadyError 應為 FileNotFoundError 子類，沿用既有 except 分支。"""
    assert issubclass(normalize_drama_script.SourceNotReadyError, FileNotFoundError)


def test_resolve_novel_text_excludes_episode_files(tmp_path):
    """串接整本時排除 episode_{N}.txt 檔案;均分結果不得包含 episode_1.txt 的內容。"""
    source_dir = tmp_path / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    whole = "甲" * 40 + "。" + "乙" * 40 + "。"
    (source_dir / "novel.md").write_text(whole, encoding="utf-8")
    (source_dir / "episode_1.txt").write_text("不該被串進來", encoding="utf-8")
    _write_project(tmp_path, [{"episode": 1}, {"episode": 2}])

    # 取第 2 集均分結果:必須是 novel.md 的後半段,絕不包含 episode_1.txt 的內容。
    result = normalize_drama_script.resolve_novel_text(tmp_path, episode=2, source=None)
    assert "不該被串進來" not in result
    assert result in whole

    with pytest.raises(FileNotFoundError) as excinfo:
        normalize_drama_script.resolve_novel_text(tmp_path, episode=1, source="")
    assert "未指定原始檔路徑" in str(excinfo.value)


def test_resolve_novel_text_multiple_explicit_sources_concatenated(tmp_path):
    """有指定複數 source 檔案時，應依序讀取並串接內容。"""
    source_dir = tmp_path / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "part1.txt").write_text("這是第一章內容。", encoding="utf-8")
    (source_dir / "part2.txt").write_text("這是第二章內容。", encoding="utf-8")
    _write_project(tmp_path, [{"episode": 1}])

    result = normalize_drama_script.resolve_novel_text(tmp_path, episode=1, source="source/part1.txt,source/part2.txt")
    assert result == "這是第一章內容。\n\n這是第二章內容。"


# --- build_normalize_prompt：細粒度參考來源篩選測試 ---


def _sample_overview():
    return {"synopsis": "概述", "genre": "奇幻", "theme": "成長", "world_setting": "魔法世界"}


def _sample_characters():
    return {"拉拉布": {"description": "主角"}, "赫爾曼": {"description": "智者"}, "梅露": {"description": "夥伴"}}


def _sample_clues():
    return {"賢者刀盾幣": {"description": "傳說神器"}}


def _sample_scenes():
    return {"鎏金城": {"description": "繁華都城"}}


def test_build_normalize_prompt_default_includes_all_blocks():
    """預設不傳新參數時，行為對齊既有：overview/style/characters/clues 都帶。"""
    prompt = normalize_drama_script.build_normalize_prompt(
        novel_text="原文",
        project_overview=_sample_overview(),
        style="動漫風",
        characters=_sample_characters(),
        clues=_sample_clues(),
    )
    assert "<overview>" in prompt
    assert "<style>" in prompt
    assert "<characters>" in prompt
    assert "<clues>" in prompt
    # scenes 預設不傳 → 不帶（向後相容）
    assert "<scenes>" not in prompt


def test_build_normalize_prompt_no_overview():
    prompt = normalize_drama_script.build_normalize_prompt(
        novel_text="原文",
        project_overview=_sample_overview(),
        style="動漫風",
        characters=_sample_characters(),
        clues=_sample_clues(),
        include_overview=False,
    )
    assert "<overview>" not in prompt
    assert "<style>" in prompt


def test_build_normalize_prompt_empty_characters_omits_section():
    prompt = normalize_drama_script.build_normalize_prompt(
        novel_text="原文",
        project_overview=_sample_overview(),
        style="動漫風",
        characters={},
        clues=_sample_clues(),
    )
    assert "<characters>" not in prompt
    assert "<clues>" in prompt


def test_build_normalize_prompt_filtered_characters_only_listed():
    chars = _sample_characters()
    only_one = {"拉拉布": chars["拉拉布"]}
    prompt = normalize_drama_script.build_normalize_prompt(
        novel_text="原文",
        project_overview=_sample_overview(),
        style="動漫風",
        characters=only_one,
        clues=_sample_clues(),
    )
    assert "拉拉布" in prompt
    assert "赫爾曼" not in prompt


def test_build_normalize_prompt_includes_scenes_block():
    prompt = normalize_drama_script.build_normalize_prompt(
        novel_text="原文",
        project_overview=_sample_overview(),
        style="動漫風",
        characters=_sample_characters(),
        clues=_sample_clues(),
        scenes=_sample_scenes(),
    )
    assert "<scenes>" in prompt
    assert "鎏金城" in prompt


def test_filter_by_names_normalize_helper():
    """drama 端也有同樣語意的 helper。"""
    assert normalize_drama_script._filter_by_names({"A": 1}, None) == {"A": 1}
    assert normalize_drama_script._filter_by_names({"A": 1}, "") == {}
    assert normalize_drama_script._filter_by_names({"A": 1, "B": 2}, "A") == {"A": 1}
    # 不存在的名字靜默忽略(用 U+001F 分隔)
    assert normalize_drama_script._filter_by_names({"A": 1}, "A\x1fX") == {"A": 1}
    items = {"史密斯, 約翰": 1, " 拉拉布 ": 2}
    assert normalize_drama_script._filter_by_names(items, "史密斯, 約翰\x1f 拉拉布 ") == items


def test_build_normalize_prompt_with_num_segments():
    prompt = normalize_drama_script.build_normalize_prompt(
        novel_text="原文",
        project_overview=_sample_overview(),
        style="動漫風",
        characters=_sample_characters(),
        clues=_sample_clues(),
        num_segments=8,
    )
    assert "指定場景數量" in prompt
    assert "改編並拆分為**剛好 8** 個場景" in prompt
    assert "E{集數}S01 到 E{集數}S08" in prompt
