"""共用向量測試（Python 端）。

與 frontend/src/utils/entity-matching.vectors.test.ts 讀同一份
tests/fixtures/entity_matching_vectors.json。任一端行為漂移即測試紅。
新增案例只改該 JSON，前後端自動同步覆蓋。
"""

import json
from pathlib import Path

import pytest

from lib.entity_matching import scan_entity_mentions

_VECTORS = json.loads(
    (Path(__file__).parent / "fixtures" / "entity_matching_vectors.json").read_text(encoding="utf-8")
)["cases"]


@pytest.mark.parametrize("case", _VECTORS, ids=[c["name"] for c in _VECTORS])
def test_shared_vector(case):
    result = scan_entity_mentions(
        case["text"],
        case.get("characters") or {},
        case.get("clues") or {},
        case.get("scenes") or {},
    )
    expected = case["expected"]
    assert sorted(result.character_names) == sorted(expected["characterNames"]), case["name"]
    assert sorted(result.clue_names) == sorted(expected["clueNames"]), case["name"]
    assert result.scene_name == expected["sceneName"], case["name"]
