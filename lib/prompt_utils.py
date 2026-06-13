"""
Prompt 工具函式

提供結構化 Prompt 到 YAML 格式的轉換功能。
"""

import yaml

# 預設選項定義
STYLES = ["Photographic", "Anime", "3D Animation"]

SHOT_TYPES = [
    "Extreme Close-up",
    "Close-up",
    "Medium Close-up",
    "Medium Shot",
    "Medium Long Shot",
    "Long Shot",
    "Extreme Long Shot",
    "Over-the-shoulder",
    "Point-of-view",
]

CAMERA_MOTIONS = [
    "Static",
    "Pan Left",
    "Pan Right",
    "Tilt Up",
    "Tilt Down",
    "Zoom In",
    "Zoom Out",
    "Tracking Shot",
]


def image_prompt_to_yaml(image_prompt: dict, project_style: str) -> str:
    """
    將 imagePrompt 結構轉換為 YAML 格式字串

    Args:
        image_prompt: segment 中的 image_prompt 物件，結構為：
            {
                "scene": "場景描述",
                "composition": {
                    "shot_type": "鏡頭型別",
                    "lighting": "光線描述",
                    "ambiance": "氛圍描述"
                }
            }
        project_style: 專案級風格設定（從 project.json 讀取）

    Returns:
        YAML 格式字串，用於 Gemini API 呼叫
    """
    ordered = {
        "Style": project_style,
        "Scene": image_prompt["scene"],
        "Composition": {
            "shot_type": image_prompt["composition"]["shot_type"],
            "lighting": image_prompt["composition"]["lighting"],
            "ambiance": image_prompt["composition"]["ambiance"],
        },
    }
    return yaml.dump(ordered, allow_unicode=True, default_flow_style=False, sort_keys=False)


def video_prompt_to_yaml(video_prompt: dict) -> str:
    """
    將 videoPrompt 結構轉換為 YAML 格式字串

    Args:
        video_prompt: segment 中的 video_prompt 物件，結構為：
            {
                "action": "動作描述",
                "camera_motion": "攝像機運動",
                "ambiance_audio": "環境音效描述",
                "dialogue": [{"speaker": "角色名", "line": "臺詞"}]
            }

    Returns:
        YAML 格式字串，用於 Veo API 呼叫
    """
    dialogue = [{"Speaker": d["speaker"], "Line": d["line"]} for d in video_prompt.get("dialogue", [])]

    ordered = {
        "Action": video_prompt["action"],
        "Camera_Motion": video_prompt["camera_motion"],
        "Ambiance_Audio": video_prompt.get("ambiance_audio", ""),
    }

    # 僅在有對話時新增 Dialogue 欄位
    if dialogue:
        ordered["Dialogue"] = dialogue

    return yaml.dump(ordered, allow_unicode=True, default_flow_style=False, sort_keys=False)


def is_structured_image_prompt(image_prompt) -> bool:
    """
    檢查 image_prompt 是否為結構化格式

    Args:
        image_prompt: image_prompt 欄位值

    Returns:
        True 如果是結構化格式（dict），False 如果是舊的字串格式
    """
    return isinstance(image_prompt, dict) and "scene" in image_prompt


def is_structured_video_prompt(video_prompt) -> bool:
    """
    檢查 video_prompt 是否為結構化格式

    Args:
        video_prompt: video_prompt 欄位值

    Returns:
        True 如果是結構化格式（dict），False 如果是舊的字串格式
    """
    return isinstance(video_prompt, dict) and "action" in video_prompt


def validate_style(style: str) -> bool:
    """驗證風格是否為預設選項"""
    return style in STYLES


def validate_shot_type(shot_type: str) -> bool:
    """驗證鏡頭型別是否為預設選項"""
    return shot_type in SHOT_TYPES


def validate_camera_motion(camera_motion: str) -> bool:
    """驗證攝像機運動是否為預設選項"""
    return camera_motion in CAMERA_MOTIONS
