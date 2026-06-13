import importlib.util
import json
import sys
from pathlib import Path

import pytest


def load_split_script():
    script_path = (
        Path(__file__).resolve().parents[2]
        / "agent_runtime_profile"
        / ".claude"
        / "skills"
        / "generate-script"
        / "scripts"
        / "split_narration_segments.py"
    )
    spec = importlib.util.spec_from_file_location("split_narration_segments", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["split_narration_segments"] = module
    spec.loader.exec_module(module)
    return module


split_narration_segments = load_split_script()


def test_resolve_novel_text_normal(tmp_path):
    """案例 1：當 episode_2.txt 存在時，只讀取 episode_2.txt"""
    source_dir = tmp_path / "source"
    source_dir.mkdir(parents=True, exist_ok=True)

    (source_dir / "episode_1.txt").write_text("Episode 1 Content", encoding="utf-8")
    (source_dir / "episode_2.txt").write_text("Episode 2 Content", encoding="utf-8")
    (source_dir / "_remaining.txt").write_text("Remaining Content", encoding="utf-8")

    result = split_narration_segments.resolve_novel_text(tmp_path, episode=2, source=None)
    assert result == "Episode 2 Content"


def _write_project(project_path, episodes):
    """寫一份最小 project.json，episodes 為 [{"episode": N}, ...]。"""
    (project_path / "project.json").write_text(
        json.dumps({"episodes": episodes}, ensure_ascii=False),
        encoding="utf-8",
    )


def test_resolve_novel_text_episode2_auto_split_from_whole(tmp_path):
    """缺 episode_2.txt 且未指定 source：整本按 2 集均分，第 2 集取後半。"""
    source_dir = tmp_path / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "novel.md").write_text("甲" * 40 + "。" + "乙" * 40 + "。", encoding="utf-8")
    _write_project(tmp_path, [{"episode": 1}, {"episode": 2}])

    ep1 = split_narration_segments.resolve_novel_text(tmp_path, episode=1, source=None)
    ep2 = split_narration_segments.resolve_novel_text(tmp_path, episode=2, source=None)

    assert ep1 + ep2 == "甲" * 40 + "。" + "乙" * 40 + "。"
    assert ep1 and ep2


def test_resolve_novel_text_episode1_single_episode_uses_whole(tmp_path):
    """只有 1 集：整本即第 1 集。"""
    source_dir = tmp_path / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "novel.md").write_text("整本原文內容。", encoding="utf-8")
    _write_project(tmp_path, [{"episode": 1}])

    result = split_narration_segments.resolve_novel_text(tmp_path, episode=1, source=None)
    assert result == "整本原文內容。"


def test_resolve_novel_text_multi_source_files_concatenated(tmp_path):
    """source/ 多檔：按檔名排序串接後再均分。"""
    source_dir = tmp_path / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "01_chapter.md").write_text("第一章內容。", encoding="utf-8")
    (source_dir / "02_chapter.md").write_text("第二章內容。", encoding="utf-8")
    _write_project(tmp_path, [{"episode": 1}])

    result = split_narration_segments.resolve_novel_text(tmp_path, episode=1, source=None)
    assert result == "第一章內容。\n\n第二章內容。"


def test_resolve_novel_text_reads_legacy_encoded_source(tmp_path):
    """source/ 文字檔可能來自 Word/Windows，預處理需支援常見台灣 legacy 編碼。"""
    source_dir = tmp_path / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    content = "時間是 1980 年代的台灣夏天。\n街角的柑仔店。"
    (source_dir / "時間是 1980 年代的台灣夏天.txt").write_bytes(content.encode("cp950"))
    _write_project(tmp_path, [{"episode": 1}])

    result = split_narration_segments.resolve_novel_text(tmp_path, episode=1, source=None)

    assert result == content


def test_resolve_novel_text_excludes_remaining_txt(tmp_path):
    """串接整本時排除 _remaining.txt（分集切分的產物）。"""
    source_dir = tmp_path / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "novel.md").write_text("正文內容。", encoding="utf-8")
    (source_dir / "_remaining.txt").write_text("不該被串進來", encoding="utf-8")
    _write_project(tmp_path, [{"episode": 1}])

    result = split_narration_segments.resolve_novel_text(tmp_path, episode=1, source=None)
    assert result == "正文內容。"


def test_resolve_novel_text_empty_source_dir_raises(tmp_path):
    """source/ 完全沒有原文檔 → SourceNotReadyError。"""
    (tmp_path / "source").mkdir(parents=True, exist_ok=True)
    _write_project(tmp_path, [{"episode": 1}])

    with pytest.raises(split_narration_segments.SourceNotReadyError):
        split_narration_segments.resolve_novel_text(tmp_path, episode=1, source=None)


def test_resolve_novel_text_prefers_episode_file_over_autosplit(tmp_path):
    """episode_2.txt 存在時，仍優先用它，不走均分。"""
    source_dir = tmp_path / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "novel.md").write_text("整本不該被用。", encoding="utf-8")
    (source_dir / "episode_2.txt").write_text("第二集專屬原文。", encoding="utf-8")
    _write_project(tmp_path, [{"episode": 1}, {"episode": 2}])

    result = split_narration_segments.resolve_novel_text(tmp_path, episode=2, source=None)
    assert result == "第二集專屬原文。"


def test_resolve_novel_text_explicit_source_overrides_autosplit(tmp_path):
    """有指定 source 時，用指定的，不走均分（即使整本存在）。"""
    source_dir = tmp_path / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "novel.md").write_text("整本不該被用。", encoding="utf-8")
    (source_dir / "我指定的.txt").write_text("使用者指定的原文。", encoding="utf-8")
    _write_project(tmp_path, [{"episode": 1}, {"episode": 2}])

    result = split_narration_segments.resolve_novel_text(tmp_path, episode=2, source="source/我指定的.txt")
    assert result == "使用者指定的原文。"


def test_source_not_ready_error_is_filenotfound_subclass():
    """SourceNotReadyError 應為 FileNotFoundError 子類，沿用既有 except 分支。"""
    assert issubclass(split_narration_segments.SourceNotReadyError, FileNotFoundError)


def test_resolve_novel_text_excludes_episode_files(tmp_path):
    """串接整本時排除 episode_{N}.txt 檔案。"""
    source_dir = tmp_path / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "novel.md").write_text("正文內容。", encoding="utf-8")
    (source_dir / "episode_1.txt").write_text("不該被串進來", encoding="utf-8")
    _write_project(tmp_path, [{"episode": 2}])

    result = split_narration_segments.resolve_novel_text(tmp_path, episode=2, source=None)
    assert result == "正文內容。"


def test_resolve_novel_text_autosplit_empty_raises(tmp_path):
    """當均分出的片段為空時拋出 SourceNotReadyError。"""
    source_dir = tmp_path / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    # 原文非常短，均分成 5 集，後段集數的內容會是空的
    (source_dir / "novel.md").write_text("很短的小說。", encoding="utf-8")
    _write_project(tmp_path, [{"episode": 1}, {"episode": 2}, {"episode": 3}, {"episode": 4}, {"episode": 5}])

    with pytest.raises(split_narration_segments.SourceNotReadyError) as excinfo:
        split_narration_segments.resolve_novel_text(tmp_path, episode=5, source=None)
    assert "均分原文後第 5 集的內容為空" in str(excinfo.value)

    with pytest.raises(FileNotFoundError) as excinfo:
        split_narration_segments.resolve_novel_text(tmp_path, episode=1, source="")
    assert "未指定原始檔路徑" in str(excinfo.value)


def test_resolve_novel_text_multiple_explicit_sources_concatenated(tmp_path):
    """有指定複數 source 檔案時，應依序讀取並串接內容。"""
    source_dir = tmp_path / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "part1.txt").write_text("這是第一章內容。", encoding="utf-8")
    (source_dir / "part2.txt").write_text("這是第二章內容。", encoding="utf-8")
    _write_project(tmp_path, [{"episode": 1}])

    result = split_narration_segments.resolve_novel_text(
        tmp_path, episode=1, source="source/part1.txt,source/part2.txt"
    )
    assert result == "這是第一章內容。\n\n這是第二章內容。"


# --- build_split_prompt：細粒度參考來源篩選測試 ---


def _sample_overview():
    return {"synopsis": "概述", "genre": "奇幻", "theme": "成長", "world_setting": "魔法世界"}


def _sample_characters():
    return {
        "拉拉布": {"description": "主角"},
        "赫爾曼": {"description": "智者"},
        "梅露": {"description": "夥伴"},
    }


def _sample_clues():
    return {"賢者刀盾幣": {"description": "傳說神器"}, "羅盤": {"description": "指引方向"}}


def _sample_scenes():
    return {"鎏金城": {"description": "繁華都城"}, "黑森林": {"description": "陰森異境"}}


def test_build_split_prompt_default_includes_all_blocks():
    """預設不傳新參數時，行為對齊既有：overview/style/characters/clues 都帶。"""
    prompt = split_narration_segments.build_split_prompt(
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


def test_build_split_prompt_no_overview():
    prompt = split_narration_segments.build_split_prompt(
        novel_text="原文",
        project_overview=_sample_overview(),
        style="動漫風",
        characters=_sample_characters(),
        clues=_sample_clues(),
        include_overview=False,
    )
    assert "<overview>" not in prompt
    assert "<style>" in prompt


def test_build_split_prompt_no_style():
    prompt = split_narration_segments.build_split_prompt(
        novel_text="原文",
        project_overview=_sample_overview(),
        style="動漫風",
        characters=_sample_characters(),
        clues=_sample_clues(),
        include_style=False,
    )
    assert "<style>" not in prompt
    assert "<overview>" in prompt


def test_build_split_prompt_empty_characters_omits_section():
    """空 dict 代表「都不帶」→ 整個 <characters> 區塊省略。"""
    prompt = split_narration_segments.build_split_prompt(
        novel_text="原文",
        project_overview=_sample_overview(),
        style="動漫風",
        characters={},
        clues=_sample_clues(),
    )
    assert "<characters>" not in prompt
    assert "<clues>" in prompt


def test_build_split_prompt_filtered_characters_only_listed():
    """只篩出指定名字。"""
    chars = _sample_characters()
    only_one = {"拉拉布": chars["拉拉布"]}
    prompt = split_narration_segments.build_split_prompt(
        novel_text="原文",
        project_overview=_sample_overview(),
        style="動漫風",
        characters=only_one,
        clues=_sample_clues(),
    )
    assert "拉拉布" in prompt
    assert "赫爾曼" not in prompt
    assert "梅露" not in prompt


def test_build_split_prompt_includes_scenes_block():
    prompt = split_narration_segments.build_split_prompt(
        novel_text="原文",
        project_overview=_sample_overview(),
        style="動漫風",
        characters=_sample_characters(),
        clues=_sample_clues(),
        scenes=_sample_scenes(),
    )
    assert "<scenes>" in prompt
    assert "鎏金城" in prompt
    assert "黑森林" in prompt


def test_build_split_prompt_all_blocks_off_no_project_info_header():
    """所有區塊都關閉時「## 專案資訊」標題也省略。"""
    prompt = split_narration_segments.build_split_prompt(
        novel_text="原文",
        project_overview=_sample_overview(),
        style="動漫風",
        characters={},
        clues={},
        include_overview=False,
        include_style=False,
    )
    assert "## 專案資訊" not in prompt
    assert "<novel>" in prompt


# --- _filter_by_names helper 測試 ---


def test_filter_by_names_none_passes_through():
    items = {"A": 1, "B": 2}
    assert split_narration_segments._filter_by_names(items, None) == items


def test_filter_by_names_empty_string_returns_empty():
    assert split_narration_segments._filter_by_names({"A": 1, "B": 2}, "") == {}


def test_filter_by_names_only_selected():
    assert split_narration_segments._filter_by_names({"A": 1, "B": 2, "C": 3}, "A\x1fC") == {"A": 1, "C": 3}


def test_filter_by_names_unknown_silently_ignored():
    """陣列裡有 project.json 不存在的名字 → 靜默忽略，不報錯。"""
    assert split_narration_segments._filter_by_names({"A": 1}, "A\x1f不存在\x1fX") == {"A": 1}


def test_filter_by_names_preserves_comma_and_whitespace_in_names():
    """迴歸測試:角色名含逗號或前後空白時,split 不可拆破、不可 strip。

    bug 修復前用 ',' 當分隔符 + n.strip():
      - 名字「史密斯, 約翰」會被 split 成 ['史密斯', '約翰'] → 全 miss
      - 名字「 拉拉布 」會被 strip 成「拉拉布」→ name in items 對不上
    """
    items = {"史密斯, 約翰": 1, " 拉拉布 ": 2, "正常名": 3}
    assert split_narration_segments._filter_by_names(items, "史密斯, 約翰\x1f 拉拉布 ") == {
        "史密斯, 約翰": 1,
        " 拉拉布 ": 2,
    }


def test_build_split_prompt_with_num_segments():
    prompt = split_narration_segments.build_split_prompt(
        novel_text="原文",
        project_overview=_sample_overview(),
        style="動漫風",
        characters=_sample_characters(),
        clues=_sample_clues(),
        num_segments=5,
    )
    assert "指定片段數量" in prompt
    assert "拆分為**剛好 5** 個片段" in prompt
    assert "G01 到 G05" in prompt


def test_resolve_novel_text_docx_support(tmp_path):
    from tests.test_docx_utils import create_fake_docx_bytes

    source_dir = tmp_path / "source"
    source_dir.mkdir(parents=True, exist_ok=True)

    docx_bytes = create_fake_docx_bytes(["第一集正文", "第二段文字"])
    (source_dir / "episode_1.docx").write_bytes(docx_bytes)
    _write_project(tmp_path, [{"episode": 1}])

    result = split_narration_segments.resolve_novel_text(tmp_path, episode=1, source="source/episode_1.docx")
    assert result == "第一集正文\n第二段文字"


def test_resolve_novel_text_drama_docx_support(tmp_path):
    from tests.test_docx_utils import create_fake_docx_bytes

    # 動態載入 normalize_drama_script.py
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
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    source_dir = tmp_path / "source"
    source_dir.mkdir(parents=True, exist_ok=True)

    docx_bytes = create_fake_docx_bytes(["第一集劇本", "第二段場景"])
    (source_dir / "episode_1.docx").write_bytes(docx_bytes)
    _write_project(tmp_path, [{"episode": 1}])

    result = module.resolve_novel_text(tmp_path, episode=1, source="source/episode_1.docx")
    assert result == "第一集劇本\n第二段場景"
