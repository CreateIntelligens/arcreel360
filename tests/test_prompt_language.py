# tests/test_prompt_language.py
from lib.prompt_language import PROMPT_LANGUAGE_RULE, helper_prompt_language_clause


def test_rule_requires_traditional_chinese():
    assert "繁體中文" in PROMPT_LANGUAGE_RULE
    # JSON 鍵名/列舉值例外須明確
    assert "JSON" in PROMPT_LANGUAGE_RULE


def test_helper_clause_is_concise_and_chinese():
    clause = helper_prompt_language_clause()
    assert "繁體中文" in clause
    assert "英文" not in clause.replace("非英文", "")  # 不得殘留「輸出英文」語意
