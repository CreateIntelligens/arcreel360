"""提示詞語言規範的單一真相源。

所有「圖片/影片生成提示詞語言」的規範字串都從這裡取，避免各生成入口
各寫一份、措辭不一或被改成英文（曾發生於 helper_generate_prompt）。

註：markdown 側規範（content-modes.md / agent 系統 prompt）無法共用同一
Python 字面值，請保持文字對齊並在 content-modes.md 標註本檔為真相源。
"""

# 結構化生成（劇本）用的完整規範：要求中文輸出、JSON 鍵名/列舉值例外。
PROMPT_LANGUAGE_RULE = "**重要：所有輸出內容必須使用繁體中文。僅 JSON 鍵名和列舉值使用英文。**"


def helper_prompt_language_clause() -> str:
    """helper 提示詞生成 endpoint 用的精簡規範句（純文字輸出，非 JSON）。"""
    return "必須只輸出繁體中文 Prompt。"
