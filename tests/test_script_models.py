import pytest
from pydantic import ValidationError

from lib.script_models import (
    Composition,
    Dialogue,
    DramaEpisodeScript,
    DramaScene,
    ImagePrompt,
    NarrationEpisodeScript,
    NarrationSegment,
    VideoPrompt,
    empty_drama_scene,
    empty_drama_script,
    empty_narration_script,
    empty_narration_segment,
)


class TestScriptModels:
    def test_narration_segment_defaults_and_validation(self):
        segment = NarrationSegment(
            segment_id="E1S01",
            episode=1,
            duration_seconds=4,
            novel_text="原文",
            characters_in_segment=["姜月茴"],
            clues_in_segment=["玉佩"],
            image_prompt=ImagePrompt(
                scene="場景",
                composition=Composition(
                    shot_type="Medium Shot",
                    lighting="暖光",
                    ambiance="薄霧",
                ),
            ),
            video_prompt=VideoPrompt(
                action="轉身",
                camera_motion="Static",
                ambiance_audio="風聲",
                dialogue=[Dialogue(speaker="姜月茴", line="等等")],
            ),
        )

        assert segment.transition_to_next == "cut"
        assert segment.generated_assets.status == "pending"

    def test_duration_accepts_any_positive_int_within_range(self):
        """duration_seconds 接受 1-60 範圍內任意整數。"""
        segment = NarrationSegment(
            segment_id="E1S01",
            episode=1,
            duration_seconds=10,  # 之前會被 DurationSeconds 拒絕
            novel_text="原文",
            characters_in_segment=["姜月茴"],
            image_prompt=ImagePrompt(
                scene="場景",
                composition=Composition(shot_type="Medium Shot", lighting="暖光", ambiance="薄霧"),
            ),
            video_prompt=VideoPrompt(action="轉身", camera_motion="Static", ambiance_audio="風聲"),
        )
        assert segment.duration_seconds == 10

    def test_duration_rejects_out_of_range(self):
        """duration_seconds 拒絕範圍外的值。"""
        with pytest.raises(ValidationError):
            NarrationSegment(
                segment_id="E1S01",
                episode=1,
                duration_seconds=0,
                novel_text="原文",
                characters_in_segment=["姜月茴"],
                image_prompt=ImagePrompt(
                    scene="場景",
                    composition=Composition(shot_type="Medium Shot", lighting="暖光", ambiance="薄霧"),
                ),
                video_prompt=VideoPrompt(action="轉身", camera_motion="Static", ambiance_audio="風聲"),
            )
        with pytest.raises(ValidationError):
            NarrationSegment(
                segment_id="E1S01",
                episode=1,
                duration_seconds=61,
                novel_text="原文",
                characters_in_segment=["姜月茴"],
                image_prompt=ImagePrompt(
                    scene="場景",
                    composition=Composition(shot_type="Medium Shot", lighting="暖光", ambiance="薄霧"),
                ),
                video_prompt=VideoPrompt(action="轉身", camera_motion="Static", ambiance_audio="風聲"),
            )

    def test_drama_scene_default_duration_is_8(self):
        """DramaScene 的預設 duration_seconds 仍為 8。"""
        scene = DramaScene(
            scene_id="E1S01",
            characters_in_scene=["姜月茴"],
            image_prompt=ImagePrompt(
                scene="場景",
                composition=Composition(shot_type="Medium Shot", lighting="暖光", ambiance="薄霧"),
            ),
            video_prompt=VideoPrompt(action="前進", camera_motion="Static", ambiance_audio="雨聲"),
        )
        assert scene.duration_seconds == 8

    def test_episode_models_build_successfully(self):
        narration = NarrationEpisodeScript(
            episode=1,
            title="第一集",
            summary="摘要",
            novel={"title": "小說", "chapter": "1"},
            segments=[],
        )
        drama = DramaEpisodeScript(
            episode=1,
            title="第一集",
            summary="摘要",
            novel={"title": "小說", "chapter": "1"},
            scenes=[
                DramaScene(
                    scene_id="E1S01",
                    characters_in_scene=["姜月茴"],
                    image_prompt=ImagePrompt(
                        scene="場景",
                        composition=Composition(
                            shot_type="Medium Shot",
                            lighting="暖光",
                            ambiance="薄霧",
                        ),
                    ),
                    video_prompt=VideoPrompt(
                        action="前進",
                        camera_motion="Static",
                        ambiance_audio="雨聲",
                    ),
                )
            ],
        )

        assert narration.content_mode == "narration"
        assert drama.content_mode == "drama"
        assert drama.scenes[0].duration_seconds == 8


class TestEmptyFactories:
    def test_empty_narration_script_valid_and_empty(self):
        d = empty_narration_script(3, "我的刀盾")
        # 能通過 Pydantic 驗證
        NarrationEpisodeScript(**d)
        assert d["content_mode"] == "narration"
        assert d["episode"] == 3
        assert d["title"] == "我的刀盾"
        assert d["segments"] == []
        assert d["novel"]["title"] == "我的刀盾"

    def test_empty_drama_script_valid_and_empty(self):
        d = empty_drama_script(2, "另一集")
        DramaEpisodeScript(**d)
        assert d["content_mode"] == "drama"
        assert d["scenes"] == []

    def test_empty_narration_segment_valid(self):
        d = empty_narration_segment(1, "E1S1")
        NarrationSegment(**d)
        assert d["segment_id"] == "E1S1"
        assert d["episode"] == 1
        assert d["duration_seconds"] == 4
        assert d["novel_text"] == ""
        assert d["characters_in_segment"] == []
        assert d["image_prompt"]["composition"]["shot_type"] == "Medium Shot"

    def test_empty_drama_scene_valid(self):
        d = empty_drama_scene(2, "E2S1")
        DramaScene(**d)
        assert d["scene_id"] == "E2S1"
        assert d["duration_seconds"] == 8
        assert d["scene_type"] == "劇情"
        assert d["characters_in_scene"] == []
