from unittest.mock import MagicMock

from lib.step1_draft_sync import parse_draft_table, render_draft_table, sync_draft_to_segments, sync_segment_to_draft

# 真實 narration 表格為 6 欄：片段 | 原文 | 字數 | 時長 | 有對話 | segment_break
REAL_NARRATION_MD = (
    "## 片段拆分結果\n\n"
    "| 片段 | 原文 | 字數 | 時長 | 有對話 | segment_break |\n"
    "|------|------|------|------|--------|---------------|\n"
    "| G01 | 鎏金城的晨光總是帶著一股矛盾的氣息。 | 17 | 4s | 否 | - |\n"
    "| G02 | 東邊的貴族區飄來甜膩的燻香。 | 13 | 8s | 是 | - |\n"
)


def test_parse_and_render_roundtrip():
    md_content = (
        "| 片段 ID | 原文 | 字數 | 時長 | segment_break |\n"
        "|---|---|---|---|---|\n"
        "| G01 | 測試內容第一行 | 7 | 4 | True |\n"
        "| G02 | 測試內容第二行 | 7 | 4 | False |\n"
    )
    rows = parse_draft_table(md_content)
    assert len(rows) == 2
    assert rows[0]["id"] == "G01"
    assert rows[0]["content"] == "測試內容第一行"

    rendered = render_draft_table(rows, "narration")
    assert "測試內容第一行" in rendered
    # 原始欄位應逐字保留，不重算字數。
    assert "| 7 |" in rendered


def test_parse_preserves_six_column_cells():
    rows = parse_draft_table(REAL_NARRATION_MD)
    assert len(rows) == 2
    assert rows[0]["id"] == "G01"
    assert rows[0]["content"] == "鎏金城的晨光總是帶著一股矛盾的氣息。"
    # raw_cells 應保留 字數 / 時長 / 有對話 / segment_break 四欄。
    assert rows[0]["raw_cells"] == ["17", "4s", "否", "-"]


def test_render_preserves_dialogue_column():
    rows = parse_draft_table(REAL_NARRATION_MD)
    rendered = render_draft_table(rows, "narration")
    # 「有對話」欄與其表頭必須保留，不可被丟欄或寫進 segment_break。
    assert "有對話" in rendered
    rerows = parse_draft_table(rendered)
    assert rerows[0]["raw_cells"] == ["17", "4s", "否", "-"]
    assert rerows[1]["raw_cells"] == ["13", "8s", "是", "-"]


def test_sync_segment_preserves_other_columns(tmp_path):
    draft_dir = tmp_path / "drafts" / "episode_1"
    draft_dir.mkdir(parents=True)
    draft_file = draft_dir / "step1_segments.md"
    draft_file.write_text(REAL_NARRATION_MD, encoding="utf-8")

    sync_segment_to_draft(tmp_path, 1, "G01", "全新的原文內容", "narration")

    new_md = draft_file.read_text(encoding="utf-8")
    assert "全新的原文內容" in new_md
    rows = parse_draft_table(new_md)
    # 被改列：content 換新，其餘欄位（字數/時長/有對話/segment_break）逐字保留。
    assert rows[0]["content"] == "全新的原文內容"
    assert rows[0]["raw_cells"] == ["17", "4s", "否", "-"]
    # 未改列：完全不動。
    assert rows[1]["content"] == "東邊的貴族區飄來甜膩的燻香。"
    assert rows[1]["raw_cells"] == ["13", "8s", "是", "-"]
    # 表頭保留「有對話」。
    assert "有對話" in new_md


def test_sync_segment_handles_escaped_pipe(tmp_path):
    draft_dir = tmp_path / "drafts" / "episode_1"
    draft_dir.mkdir(parents=True)
    draft_file = draft_dir / "step1_segments.md"
    draft_file.write_text(REAL_NARRATION_MD, encoding="utf-8")

    # 新內容含字面 | ，寫回時應跳脫，讀回時還原。
    sync_segment_to_draft(tmp_path, 1, "G02", "他說：是A|還是B？", "narration")

    new_md = draft_file.read_text(encoding="utf-8")
    assert "A\\|還是B" in new_md  # 檔案中為跳脫形式
    rows = parse_draft_table(new_md)
    assert rows[1]["content"] == "他說：是A|還是B？"  # 解析後還原
    assert rows[1]["raw_cells"] == ["13", "8s", "是", "-"]


def test_sync_segment_drama_five_column(tmp_path):
    draft_dir = tmp_path / "drafts" / "episode_1"
    draft_dir.mkdir(parents=True)
    draft_file = draft_dir / "step1_normalized_script.md"
    draft_file.write_text(
        "| 場景 ID | 場景描述 | 時長 | 場景型別 | segment_break |\n"
        "|---|---|---|---|---|\n"
        "| E1S01 | 舊場景描述 | 8 | 劇情 | 是 |\n"
        "| E1S02 | 另一場景 | 8 | 對話 | 否 |\n",
        encoding="utf-8",
    )

    sync_segment_to_draft(tmp_path, 1, "E1S01", "新場景描述", "drama")

    rows = parse_draft_table(draft_file.read_text(encoding="utf-8"))
    assert rows[0]["content"] == "新場景描述"
    assert rows[0]["raw_cells"] == ["8", "劇情", "是"]
    assert rows[1]["content"] == "另一場景"


def test_sync_draft_to_segments(tmp_path):
    manager = MagicMock()

    script_data = {
        "content_mode": "narration",
        "segments": [{"segment_id": "G01", "novel_text": "舊文字"}, {"segment_id": "G02", "novel_text": "無變化"}],
    }
    manager.load_script.return_value = script_data

    new_md = (
        "| 片段 ID | 原文 | 字數 | 時長 | segment_break |\n"
        "|---|---|---|---|---|\n"
        "| G01 | 改過的文字 | 5 | 4 | True |\n"
        "| G02 | 無變化 | 3 | 4 | False |\n"
    )

    sync_draft_to_segments(tmp_path, 1, new_md, "narration", manager)

    manager.load_script.assert_called_once_with(tmp_path.name, "episode_1.json")

    manager.save_script.assert_called_once()
    saved_script = manager.save_script.call_args[0][1]
    assert saved_script["segments"][0]["novel_text"] == "改過的文字"
    assert saved_script["segments"][1]["novel_text"] == "無變化"


# 實際 normalize_drama_script 輸出的 8 欄格式：場景描述在第 7 欄、旁白/台詞在第 8 欄。
REAL_DRAMA_MD = (
    "| 場景 ID | 有對話 | 出場的角色 | 出現的道具 | 場景 | 時長 | 場景描述 | 旁白/台詞 |\n"
    "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n"
    "| E01S01 | 否 | 沈文程 | 釣竿 | 岩岸 | 8 | 沈文程站在岩岸邊。 | 釣魚是靈感的激發。 |\n"
    "| E01S02 | 是 | 沈文程 | 釣竿 | 防波堤 | 10 | 沈文程展示釣竿。 | 釣魚可以闔家參與。 |\n"
)


def test_parse_drama_eight_column_locates_description_and_narration():
    """8 欄 drama 表格：content 取「場景描述」欄、narration 取「旁白/台詞」欄，不再錯位到「有對話」。"""
    rows = parse_draft_table(REAL_DRAMA_MD)
    assert len(rows) == 2
    assert rows[0]["id"] == "E01S01"
    assert rows[0]["content"] == "沈文程站在岩岸邊。"
    assert rows[0]["narration"] == "釣魚是靈感的激發。"
    assert rows[1]["content"] == "沈文程展示釣竿。"
    assert rows[1]["narration"] == "釣魚可以闔家參與。"


def test_sync_segment_drama_eight_column_overwrites_description_column(tmp_path):
    """行內覆寫應命中「場景描述」欄（第 7 欄），而非「有對話」欄。"""
    draft_dir = tmp_path / "drafts" / "episode_1"
    draft_dir.mkdir(parents=True)
    draft_file = draft_dir / "step1_normalized_script.md"
    draft_file.write_text(REAL_DRAMA_MD, encoding="utf-8")

    assert sync_segment_to_draft(tmp_path, 1, "E01S01", "改寫後的場景描述", "drama")

    rows = parse_draft_table(draft_file.read_text(encoding="utf-8"))
    assert rows[0]["content"] == "改寫後的場景描述"
    assert rows[0]["narration"] == "釣魚是靈感的激發。"  # 旁白欄不受影響
    assert "否" in draft_file.read_text(encoding="utf-8")  # 「有對話」欄保留


def test_sync_draft_to_segments_drama_backfills_narration(tmp_path):
    """drama 同步應同時回填 scene_description 與 narration_text。"""
    manager = MagicMock()
    script_data = {
        "content_mode": "drama",
        "scenes": [
            {"scene_id": "E01S01", "scene_description": "舊描述", "narration_text": "舊旁白"},
            {"scene_id": "E01S02", "scene_description": "", "narration_text": ""},
        ],
    }
    manager.load_script.return_value = script_data

    sync_draft_to_segments(tmp_path, 1, REAL_DRAMA_MD, "drama", manager)

    saved = manager.save_script.call_args[0][1]
    assert saved["scenes"][0]["scene_description"] == "沈文程站在岩岸邊。"
    assert saved["scenes"][0]["narration_text"] == "釣魚是靈感的激發。"
    assert saved["scenes"][1]["scene_description"] == "沈文程展示釣竿。"
    assert saved["scenes"][1]["narration_text"] == "釣魚可以闔家參與。"


# 新版 9 欄格式：旁白與對話分流成獨立兩欄，移除「有對話」旗標。
NEW_DRAMA_MD = (
    "| 場景 ID | 場景描述 | 旁白 | 對話 | 出場的角色 | 出現的道具 | 場景 | 時長 | segment_break |\n"
    "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n"
    "| E01S01 | 沈文程站在岩岸邊。 | 釣魚是靈感的激發。 | - | 沈文程 | 釣竿 | 岩岸 | 8 | 是 |\n"
    "| E01S02 | 兩人在防波堤交談。 | - | 小明：你看那邊！<br>小華：真的耶！ | 小明, 小華 | - | 防波堤 | 8 | 否 |\n"
)


def test_parse_drama_nine_column_locates_description_and_narration():
    """新版 9 欄（含獨立「對話」欄）：content 取「場景描述」、narration 取「旁白」，不受欄序變動影響。"""
    rows = parse_draft_table(NEW_DRAMA_MD)
    assert len(rows) == 2
    assert rows[0]["content"] == "沈文程站在岩岸邊。"
    assert rows[0]["narration"] == "釣魚是靈感的激發。"
    assert rows[1]["content"] == "兩人在防波堤交談。"
    assert rows[1]["narration"] == "-"


def test_sync_segment_drama_nine_column_overwrites_description(tmp_path):
    """新版 9 欄行內覆寫應命中「場景描述」欄，旁白欄不受影響。"""
    draft_dir = tmp_path / "drafts" / "episode_1"
    draft_dir.mkdir(parents=True)
    draft_file = draft_dir / "step1_normalized_script.md"
    draft_file.write_text(NEW_DRAMA_MD, encoding="utf-8")

    assert sync_segment_to_draft(tmp_path, 1, "E01S02", "改寫後的場景描述", "drama")

    rows = parse_draft_table(draft_file.read_text(encoding="utf-8"))
    assert rows[1]["content"] == "改寫後的場景描述"
    assert rows[1]["narration"] == "-"
    # 「對話」欄內容應原樣保留在草稿（供生成劇本時由 LLM 讀取轉 dialogue）。
    assert "小明：你看那邊！<br>小華：真的耶！" in draft_file.read_text(encoding="utf-8")


def test_sync_script_to_draft_file_narration(tmp_path):
    from lib.step1_draft_sync import sync_script_to_draft_file

    manager = MagicMock()
    manager.load_script.return_value = {
        "content_mode": "narration",
        "segments": [
            {
                "segment_id": "E1S01",
                "novel_text": "測試原文1",
                "duration_seconds": 6,
                "video_prompt": {"dialogue": [{"speaker": "A", "line": "哈囉"}]},
                "segment_break": True,
            }
        ],
    }

    # Mock manager.get_project_path
    manager.get_project_path.return_value = tmp_path

    assert sync_script_to_draft_file(tmp_path, 1, "narration", manager)

    draft_file = tmp_path / "drafts" / "episode_1" / "step1_segments.md"
    assert draft_file.exists()
    content = draft_file.read_text(encoding="utf-8")
    assert "G01" in content
    assert "測試原文1" in content
    assert "6s" in content
    assert "是" in content


def test_sync_script_to_draft_file_drama(tmp_path):
    from lib.step1_draft_sync import sync_script_to_draft_file

    manager = MagicMock()
    manager.load_script.return_value = {
        "content_mode": "drama",
        "scenes": [
            {
                "scene_id": "E1S01",
                "scene_description": "場景描述測試",
                "narration_text": "旁白測試",
                "video_prompt": {"dialogue": [{"speaker": "李明", "line": "你好"}]},
                "characters_in_scene": ["李明"],
                "clues_in_scene": ["釣竿"],
                "scene_in_scene": "岩岸",
                "duration_seconds": 8,
                "segment_break": True,
            }
        ],
    }

    manager.get_project_path.return_value = tmp_path

    assert sync_script_to_draft_file(tmp_path, 1, "drama", manager)

    draft_file = tmp_path / "drafts" / "episode_1" / "step1_normalized_script.md"
    assert draft_file.exists()
    content = draft_file.read_text(encoding="utf-8")
    assert "E1S01" in content
    assert "場景描述測試" in content
    assert "旁白測試" in content
    assert "李明" in content
    assert "釣竿" in content
    assert "岩岸" in content
    assert "8" in content
    assert "是" in content
