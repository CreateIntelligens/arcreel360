"""entity_reconciler 模組測試。"""

import copy

from lib.entity_matching import build_sorted_entries
from lib.entity_reconciler import reconcile_item, reconcile_script

PROJECT_JSON = {
    "characters": {"阿克 (Arke)": {}, "小明": {}},
    "clues": {"兔熊玩偶": {}, "青玉碎片（Jade Shard）": {}},
    "scenes": {"古城": {}, "荒野 (Wasteland)": {}},
}

ENTRIES = build_sorted_entries(PROJECT_JSON["characters"], PROJECT_JSON["clues"], PROJECT_JSON["scenes"])


def _segment(**overrides):
    base = {
        "segment_id": "E1S1",
        "novel_text": "",
        "characters_in_segment": [],
        "clues_in_segment": [],
        "scene_in_segment": None,
        "image_prompt": {"scene": ""},
        "video_prompt": {"action": ""},
    }
    base.update(overrides)
    return base


NARRATION_FIELDS = ("characters_in_segment", "clues_in_segment", "scene_in_segment")


class TestReconcileItem:
    def test_fills_missing_character_from_novel_text(self):
        seg = _segment(novel_text="小明走進了房間")
        out = reconcile_item(seg, ENTRIES, fields=NARRATION_FIELDS)
        assert out["characters_in_segment"] == ["小明"]

    def test_fills_missing_clue_from_image_prompt(self):
        seg = _segment(image_prompt={"scene": "桌上放著兔熊玩偶"})
        out = reconcile_item(seg, ENTRIES, fields=NARRATION_FIELDS)
        assert out["clues_in_segment"] == ["兔熊玩偶"]

    def test_fills_from_video_prompt_action(self):
        seg = _segment(video_prompt={"action": "Arke 拔出了刀"})
        out = reconcile_item(seg, ENTRIES, fields=NARRATION_FIELDS)
        assert out["characters_in_segment"] == ["阿克 (Arke)"]

    def test_union_keeps_ai_filled_and_appends(self):
        """union：AI 已填的保留，新命中追加，順序穩定。"""
        seg = _segment(novel_text="小明拿著兔熊玩偶", characters_in_segment=["既有角色"])
        out = reconcile_item(seg, ENTRIES, fields=NARRATION_FIELDS)
        assert out["characters_in_segment"] == ["既有角色", "小明"]
        assert out["clues_in_segment"] == ["兔熊玩偶"]

    def test_never_removes_existing(self):
        """AI 填了正文沒提到的關聯也不移除。"""
        seg = _segment(novel_text="一段沒有已知名稱的文字", clues_in_segment=["神秘道具"])
        out = reconcile_item(seg, ENTRIES, fields=NARRATION_FIELDS)
        assert out["clues_in_segment"] == ["神秘道具"]

    def test_no_duplicate_when_already_present(self):
        seg = _segment(novel_text="小明出場", characters_in_segment=["小明"])
        out = reconcile_item(seg, ENTRIES, fields=NARRATION_FIELDS)
        assert out["characters_in_segment"] == ["小明"]

    def test_scene_filled_only_when_empty(self):
        seg = _segment(novel_text="他們來到古城")
        out = reconcile_item(seg, ENTRIES, fields=NARRATION_FIELDS)
        assert out["scene_in_segment"] == "古城"

    def test_scene_not_overwritten_when_present(self):
        seg = _segment(novel_text="他們來到古城", scene_in_segment="既有場景")
        out = reconcile_item(seg, ENTRIES, fields=NARRATION_FIELDS)
        assert out["scene_in_segment"] == "既有場景"

    def test_input_not_mutated(self):
        seg = _segment(novel_text="小明出場")
        snapshot = copy.deepcopy(seg)
        reconcile_item(seg, ENTRIES, fields=NARRATION_FIELDS)
        assert seg == snapshot

    def test_empty_text_noop(self):
        seg = _segment()
        out = reconcile_item(seg, ENTRIES, fields=NARRATION_FIELDS)
        assert out["characters_in_segment"] == []
        assert out["scene_in_segment"] is None


class TestReconcileScript:
    def test_narration_script(self):
        script = {
            "content_mode": "narration",
            "segments": [_segment(novel_text="小明拿起兔熊玩偶走進古城")],
        }
        out = reconcile_script(script, PROJECT_JSON)
        seg = out["segments"][0]
        assert seg["characters_in_segment"] == ["小明"]
        assert seg["clues_in_segment"] == ["兔熊玩偶"]
        assert seg["scene_in_segment"] == "古城"

    def test_drama_script(self):
        script = {
            "content_mode": "drama",
            "scenes": [
                {
                    "scene_id": "E1S1",
                    "novel_text": "小明出現",
                    "characters_in_scene": [],
                    "clues_in_scene": [],
                    "scene_in_scene": None,
                    "image_prompt": {"scene": ""},
                    "video_prompt": {"action": ""},
                }
            ],
        }
        out = reconcile_script(script, PROJECT_JSON)
        assert out["scenes"][0]["characters_in_scene"] == ["小明"]

    def test_empty_project_json_noop(self):
        script = {"content_mode": "narration", "segments": [_segment(novel_text="小明出場")]}
        out = reconcile_script(script, {})
        assert out["segments"][0]["characters_in_segment"] == []

    def test_none_scenes_in_project_json(self):
        script = {"content_mode": "narration", "segments": [_segment(novel_text="小明出場")]}
        pj = {"characters": {"小明": {}}, "clues": {}, "scenes": None}
        out = reconcile_script(script, pj)
        assert out["segments"][0]["characters_in_segment"] == ["小明"]

    def test_script_input_not_mutated(self):
        script = {"content_mode": "narration", "segments": [_segment(novel_text="小明出場")]}
        snapshot = copy.deepcopy(script)
        reconcile_script(script, PROJECT_JSON)
        assert script == snapshot

    def test_missing_segments_key_noop(self):
        script = {"content_mode": "narration"}
        out = reconcile_script(script, PROJECT_JSON)
        assert out == {"content_mode": "narration"}
