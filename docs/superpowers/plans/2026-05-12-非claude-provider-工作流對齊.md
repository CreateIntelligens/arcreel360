# 非 Claude provider 工作流對齊 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把分集切分（peek/split）與拆段（preprocess）的核心邏輯收斂到 `lib/`，讓 gemini-full / openai-full agent 取得對應 function（與 Claude 能力對等），並新增前端可觸發的分集切分 HTTP API + UI。

**Architecture:** 純文字運算抽到 `lib/episode_splitter.py`（無 I/O）；落地（寫檔 + 更新 project.json）放 `ProjectManager.commit_episode_split`；三條呼叫路徑——Claude CLI 腳本（改成薄 wrapper）、gemini/openai function handler（`skill_function_declarations.py`，adapter 自動傳播）、HTTP API（`projects.py`）——共用同一份 lib 邏輯。preprocess 走類似結構（`lib/episode_preprocess.py` 包既有 subprocess 模式）。

**Tech Stack:** Python 3.12 + uv + pytest（`asyncio_mode=auto`）+ ruff（line-length 120）；FastAPI；React 19 + Vitest + Testing Library（前端用 Node 22 / pnpm 11.1.0：`export PATH="$HOME/.nvm/versions/node/v22.21.1/bin:$PATH"` + `CI=true COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack pnpm@11.1.0 ...`，在 `frontend/` 目錄）。

**設計文件：** `docs/superpowers/specs/2026-05-12-非claude-provider-工作流對齊-design.md`

**回覆/commit 一律繁體中文（repo 規範）。**

---

## 檔案結構

新增：
- `lib/episode_splitter.py` — 純文字運算：`count_chars` / `find_char_offset` / `find_natural_breakpoints` / `find_anchor_near_target` / `peek_split` / `split_episode_text`
- `lib/episode_preprocess.py` — `run_preprocess(project_path, episode) -> dict`（包既有 subprocess 模式）
- `tests/test_episode_splitter.py`
- `tests/test_episode_split_routes.py`
- `tests/test_episode_split_skill.py`
- `frontend/src/components/canvas/timeline/EpisodeSplitPanel.tsx`
- `frontend/src/components/canvas/timeline/EpisodeSplitPanel.test.tsx`

修改：
- `agent_runtime_profile/.claude/skills/manage-project/scripts/_text_utils.py` → re-export from `lib.episode_splitter`
- `agent_runtime_profile/.claude/skills/manage-project/scripts/peek_split_point.py` → 薄 wrapper
- `agent_runtime_profile/.claude/skills/manage-project/scripts/split_episode.py` → 薄 wrapper
- `lib/project_manager.py` → +`commit_episode_split`（不拆 ProjectManager；spec 允許的「逃生口」選項）
- `server/agent_runtime/skill_function_declarations.py` → +3 handler/decl（`peek_split_point` / `split_episode` / `preprocess_episode`）
- `server/routers/projects.py` → +2 路由（`POST .../episodes/peek`、`.../episodes/split`），`preprocess_episode` 改呼叫 `lib.episode_preprocess`
- `agent_runtime_profile/.claude/skills/manage-project/SKILL.md` → 同步說明
- `agent_runtime_profile/CLAUDE.md` → 角色/線索提取引導文字
- `frontend/src/api.ts` → +2 method
- `frontend/src/components/canvas/timeline/TimelineCanvas.tsx` → 掛載 `EpisodeSplitPanel`

> **決策固定**：ProjectManager 不拆（直接加 `commit_episode_split` 方法）。`split_narration_segments.py` / `normalize_drama_script.py` 不改（`lib/episode_preprocess.py` 用 subprocess 呼叫它們，跟既有 `preprocess_episode` 路由一致）。`lib/project_episodes.py` 不建。

---

## 階段一：`lib/episode_splitter.py` + CLI 腳本改 wrapper

### Task 1：建立 `lib/episode_splitter.py` 的文字工具函式（從 `_text_utils.py` 搬移）

**Files:**
- Create: `lib/episode_splitter.py`
- Test: `tests/test_episode_splitter.py`

- [ ] **Step 1：寫失敗測試**

```python
# tests/test_episode_splitter.py
from lib.episode_splitter import count_chars, find_char_offset, find_natural_breakpoints


def test_count_chars_skips_blank_lines():
    text = "abc\n\n  \ndef"
    assert count_chars(text) == 6  # "abc" + "def"，空行與純空白行不計


def test_count_chars_includes_punctuation():
    assert count_chars("你好，世界！") == 6


def test_find_char_offset_basic():
    text = "abcde"
    # 第 3 個有效字元 → offset 2（0-based）
    assert find_char_offset(text, 3) == 2


def test_find_char_offset_skips_blank_line():
    text = "ab\n\ncd"  # 有效字元: a b c d；c 是第 3 個
    # offset: a=0 b=1 \n=2 \n=3 c=4 d=5 → 第 3 個有效字元在 offset 4
    assert find_char_offset(text, 3) == 4


def test_find_char_offset_overflow_returns_end():
    text = "abc"
    assert find_char_offset(text, 999) == len(text)


def test_find_natural_breakpoints_finds_sentence_end():
    text = "他轉身。她跟上。"
    bps = find_natural_breakpoints(text, center_offset=4, window=10)
    # 至少有兩個 sentence 斷點（。之後）
    assert any(bp["type"] == "sentence" for bp in bps)
    # 按距離排序
    assert bps == sorted(bps, key=lambda b: b["distance"])


def test_find_natural_breakpoints_finds_paragraph():
    text = "第一段。\n\n第二段。"
    bps = find_natural_breakpoints(text, center_offset=len("第一段。\n"), window=10)
    assert any(bp["type"] == "paragraph" for bp in bps)
```

- [ ] **Step 2：跑測試確認失敗**

Run: `uv run python -m pytest tests/test_episode_splitter.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'lib.episode_splitter'`）

- [ ] **Step 3：實作 `lib/episode_splitter.py`（文字工具部分）**

把 `agent_runtime_profile/.claude/skills/manage-project/scripts/_text_utils.py` 的三個函式逐字搬過來（`count_chars` / `find_char_offset` / `find_natural_breakpoints`），加上 module docstring：

```python
# lib/episode_splitter.py
"""分集切分核心：純文字運算（無 I/O、無 cwd 假設）。

供三條路徑共用：
- Claude CLI 腳本（agent_runtime_profile/.claude/skills/manage-project/scripts/*.py，薄 wrapper）
- gemini/openai function handler（server/agent_runtime/skill_function_declarations.py）
- HTTP API（server/routers/projects.py）

計數規則：含標點，不含空行（純空白行不計入字數）。
"""

from __future__ import annotations


def count_chars(text: str) -> int:
    """計算有效字數：所有非空行中的字元總數（含標點，不含空行）。"""
    total = 0
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped:
            total += len(stripped)
    return total


def find_char_offset(text: str, target_count: int) -> int:
    """將有效字數轉換為原文字元偏移位置（0-based）。target_count 超界 → 回文字末尾。"""
    counted = 0
    lines = text.split("\n")
    pos = 0
    for line_idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            pos += len(line)
            if line_idx < len(lines) - 1:
                pos += 1
            continue
        for char in line:
            if not char.strip():
                pos += 1
                continue
            counted += 1
            if counted >= target_count:
                return pos
            pos += 1
        if line_idx < len(lines) - 1:
            pos += 1
    return pos


def find_natural_breakpoints(text: str, center_offset: int, window: int = 200) -> list[dict]:
    """在指定偏移附近查詢自然斷點（句末標點、段落邊界）。回 [{offset, char, type, distance}]，按 distance 排序。"""
    start = max(0, center_offset - window)
    end = min(len(text), center_offset + window)
    sentence_endings = {"。", "！", "？", "…"}
    breakpoints: list[dict] = []
    for i in range(start, end):
        ch = text[i]
        if ch == "\n" and i + 1 < len(text) and text[i + 1] == "\n":
            breakpoints.append({"offset": i + 1, "char": "\\n\\n", "type": "paragraph", "distance": abs(i + 1 - center_offset)})
        elif ch in sentence_endings:
            breakpoints.append({"offset": i + 1, "char": ch, "type": "sentence", "distance": abs(i + 1 - center_offset)})
    breakpoints.sort(key=lambda bp: bp["distance"])
    return breakpoints
```

- [ ] **Step 4：跑測試確認通過**

Run: `uv run python -m pytest tests/test_episode_splitter.py -v`
Expected: PASS（6 個測試）

---

### Task 2：`lib/episode_splitter.py` 加 `peek_split` + `find_anchor_near_target` + `split_episode_text`

**Files:**
- Modify: `lib/episode_splitter.py`
- Test: `tests/test_episode_splitter.py`

- [ ] **Step 1：寫失敗測試（追加到 `tests/test_episode_splitter.py`）**

```python
import pytest
from lib.episode_splitter import peek_split, split_episode_text


def test_peek_split_returns_context_and_breakpoints():
    text = "甲" * 10 + "。" + "乙" * 10
    result = peek_split(text, target_chars=10, context=5)
    assert result["total_chars"] == 21
    assert result["target_chars"] == 10
    assert "context_before" in result and "context_after" in result
    assert isinstance(result["nearby_breakpoints"], list)


def test_peek_split_target_overflow_raises():
    with pytest.raises(ValueError, match="超過|exceed"):
        peek_split("短文", target_chars=100)


def test_split_episode_text_basic():
    text = "前半段落。他轉身離開了。後半段落。"
    result = split_episode_text(text, target_chars=8, anchor="他轉身離開了。", context=20)
    assert result["part_before"].endswith("他轉身離開了。")
    assert result["part_after"].startswith("後半段落。")
    assert result["split_pos"] == len("前半段落。他轉身離開了。")
    assert "前半段落。他轉身離開了。"[-min(50, len(result["part_before"])):] == result["before_preview"][-min(50, len(result["before_preview"])):] or result["before_preview"] in result["part_before"]


def test_split_episode_text_anchor_not_found_raises():
    with pytest.raises(ValueError, match="未找到錨點|anchor"):
        split_episode_text("一些文字內容。", target_chars=3, anchor="不存在的錨點", context=50)


def test_split_episode_text_anchor_multiple_picks_nearest():
    # anchor 出現兩次，選距離 target 較近的
    text = "錨點AB" + "X" * 20 + "錨點AB" + "Y" * 5
    target_offset_chars = len("錨點AB") + 20 + 1  # 接近第二個錨點
    result = split_episode_text(text, target_chars=target_offset_chars, anchor="錨點AB", context=30)
    # 第二個錨點末尾
    assert result["split_pos"] == len("錨點AB") + 20 + len("錨點AB")
```

- [ ] **Step 2：跑測試確認失敗**

Run: `uv run python -m pytest tests/test_episode_splitter.py -v -k "peek_split or split_episode_text"`
Expected: FAIL（`ImportError: cannot import name 'peek_split'`）

- [ ] **Step 3：實作（追加到 `lib/episode_splitter.py`）**

```python
def find_anchor_near_target(text: str, anchor: str, target_offset: int, window: int = 500) -> list[int]:
    """在 target_offset 附近視窗內查 anchor，回匹配「末尾」偏移列表（按距 target 排序）。"""
    search_start = max(0, target_offset - window)
    search_end = min(len(text), target_offset + window)
    region = text[search_start:search_end]
    positions: list[int] = []
    start = 0
    while True:
        idx = region.find(anchor, start)
        if idx == -1:
            break
        positions.append(search_start + idx + len(anchor))
        start = idx + 1
    positions.sort(key=lambda p: abs(p - target_offset))
    return positions


def peek_split(source_text: str, target_chars: int, context: int = 200) -> dict:
    """預覽分集切分點（read-only）。target_chars >= 總有效字數 → ValueError。

    回 {total_chars, target_chars, target_offset, context_before, context_after, nearby_breakpoints}。
    （key 名與既有 peek_split_point.py 的 JSON 輸出一致，但不含 'source'。）
    """
    total_chars = count_chars(source_text)
    if target_chars >= total_chars:
        raise ValueError(f"目標字數 ({target_chars}) 超過或等於總有效字數 ({total_chars})")
    target_offset = find_char_offset(source_text, target_chars)
    breakpoints = find_natural_breakpoints(source_text, target_offset, window=context)
    ctx_start = max(0, target_offset - context)
    ctx_end = min(len(source_text), target_offset + context)
    return {
        "total_chars": total_chars,
        "target_chars": target_chars,
        "target_offset": target_offset,
        "context_before": source_text[ctx_start:target_offset],
        "context_after": source_text[target_offset:ctx_end],
        "nearby_breakpoints": breakpoints[:10],
    }


def split_episode_text(source_text: str, target_chars: int, anchor: str, context: int = 500) -> dict:
    """用 anchor 在 target 附近精確定位切點，回兩半文字。

    anchor 找不到 → ValueError。anchor 多個 → 選距 target 最近的（不報錯）。
    回 {split_pos, part_before, part_after, before_preview, after_preview, anchor_match_count, target_offset}。
    """
    target_offset = find_char_offset(source_text, target_chars)
    positions = find_anchor_near_target(source_text, anchor, target_offset, window=context)
    if not positions:
        raise ValueError(
            f'在目標字數 {target_chars} 附近（±{context} 字元視窗）未找到錨點文字: "{anchor}"'
        )
    split_pos = positions[0]
    part_before = source_text[:split_pos]
    part_after = source_text[split_pos:]
    preview_len = 50
    return {
        "split_pos": split_pos,
        "part_before": part_before,
        "part_after": part_after,
        "before_preview": part_before[-preview_len:] if len(part_before) > preview_len else part_before,
        "after_preview": part_after[:preview_len] if len(part_after) > preview_len else part_after,
        "anchor_match_count": len(positions),
        "target_offset": target_offset,
    }
```

- [ ] **Step 4：跑測試確認通過**

Run: `uv run python -m pytest tests/test_episode_splitter.py -v`
Expected: PASS（全部）

---

### Task 3：`_text_utils.py` 改成 re-export，驗證 Claude CLI 腳本回歸

**Files:**
- Modify: `agent_runtime_profile/.claude/skills/manage-project/scripts/_text_utils.py`

- [ ] **Step 1：先記錄改前的腳本輸出（基準）**

```bash
cd ~/arcreel360
# 用 smoketest 專案的 source（若不存在，先建一個臨時 txt）
mkdir -p /tmp/eptest && printf '甲%.0s' {1..50} > /tmp/eptest/n.txt && printf '。' >> /tmp/eptest/n.txt && printf '乙%.0s' {1..50} >> /tmp/eptest/n.txt
cd /tmp/eptest
uv run python ~/arcreel360/agent_runtime_profile/.claude/skills/manage-project/scripts/peek_split_point.py --source n.txt --target 30 > /tmp/eptest/peek_before.txt 2>&1
uv run python ~/arcreel360/agent_runtime_profile/.claude/skills/manage-project/scripts/split_episode.py --source n.txt --episode 1 --target 30 --anchor "甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲" --dry-run > /tmp/eptest/split_before.txt 2>&1
cat /tmp/eptest/peek_before.txt /tmp/eptest/split_before.txt
cd ~/arcreel360
```

（記住這兩個輸出，Step 4 比對。anchor 用前 30 個「甲」確保能在 target 附近找到。）

- [ ] **Step 2：改 `_text_utils.py`**

```python
# agent_runtime_profile/.claude/skills/manage-project/scripts/_text_utils.py
"""_text_utils.py - 分集切分共享工具函式（re-export 自 lib.episode_splitter）。

歷史上此模組是真相源；現已收斂到 lib/episode_splitter.py，此處保留以維持
peek_split_point.py / split_episode.py 的 import 路徑不變。
"""

import sys
from pathlib import Path

# 確保能 import 到 repo 的 lib/（腳本執行時 cwd 是專案目錄，不一定在 sys.path）
_REPO_ROOT = Path(__file__).resolve().parents[5]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from lib.episode_splitter import (  # noqa: E402,F401
    count_chars,
    find_anchor_near_target,
    find_char_offset,
    find_natural_breakpoints,
)
```

> 註：`parents[5]` —— `agent_runtime_profile/.claude/skills/manage-project/scripts/_text_utils.py` 往上 5 層 = repo root。實作時用 `python -c` 驗證一下層數對不對：`python -c "from pathlib import Path; print(Path('agent_runtime_profile/.claude/skills/manage-project/scripts/_text_utils.py').resolve().parents[5])"`（在 repo root 跑，應印出 repo root）。

- [ ] **Step 3：`split_episode.py` 的 `find_anchor_near_target` 改成 import（移除本地定義）**

`split_episode.py` 目前自己定義了 `find_anchor_near_target`。改成從 `_text_utils` import（`_text_utils` 已 re-export 自 lib），移除本地函式定義：

```python
# split_episode.py 開頭附近：
sys.path.insert(0, str(Path(__file__).parent))
from _text_utils import find_anchor_near_target, find_char_offset  # noqa: E402
```

並刪掉 `split_episode.py` 裡 `def find_anchor_near_target(...)` 那整段。其餘 `main()` 不動。

- [ ] **Step 4：跑改後腳本，逐字比對輸出**

```bash
cd /tmp/eptest
uv run python ~/arcreel360/agent_runtime_profile/.claude/skills/manage-project/scripts/peek_split_point.py --source n.txt --target 30 > /tmp/eptest/peek_after.txt 2>&1
uv run python ~/arcreel360/agent_runtime_profile/.claude/skills/manage-project/scripts/split_episode.py --source n.txt --episode 1 --target 30 --anchor "甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲甲" --dry-run > /tmp/eptest/split_after.txt 2>&1
diff /tmp/eptest/peek_before.txt /tmp/eptest/peek_after.txt && echo "peek 輸出一致 ✓"
diff /tmp/eptest/split_before.txt /tmp/eptest/split_after.txt && echo "split 輸出一致 ✓"
cd ~/arcreel360
```

Expected: 兩個 diff 都無輸出（逐字一致）。若不一致 → 修到一致為止（這是 Claude provider 回歸驗收項，不可放過）。

- [ ] **Step 5：ruff**

```bash
uv run ruff check agent_runtime_profile/ lib/ && uv run ruff format agent_runtime_profile/ lib/
```

---

## 階段二：`ProjectManager.commit_episode_split` + gemini/openai function handlers

### Task 4：`ProjectManager.commit_episode_split`

**Files:**
- Modify: `lib/project_manager.py`（在 `add_episode` 附近加新方法）
- Test: `tests/test_project_manager_more.py`（追加）

- [ ] **Step 1：寫失敗測試（追加到 `tests/test_project_manager_more.py`）**

```python
def test_commit_episode_split_writes_files_and_updates_project(tmp_path):
    from lib.project_manager import ProjectManager
    pm = ProjectManager(projects_root=str(tmp_path / "projects"))
    pm.create_project("demo")
    pm.create_project_metadata("demo", title="t", style="anime", content_mode="narration")
    proj_dir = pm.get_project_path("demo")
    (proj_dir / "source").mkdir(exist_ok=True)
    (proj_dir / "source" / "novel.txt").write_text("前半。後半。", encoding="utf-8")

    result = pm.commit_episode_split(
        "demo", source_rel="source/novel.txt", episode=1,
        part_before="前半。", part_after="後半。", title="第一集",
    )

    assert (proj_dir / "source" / "episode_1.txt").read_text(encoding="utf-8") == "前半。"
    assert (proj_dir / "source" / "_remaining.txt").read_text(encoding="utf-8") == "後半。"
    # 原始檔未被修改
    assert (proj_dir / "source" / "novel.txt").read_text(encoding="utf-8") == "前半。後半。"
    # project.json episodes 多一筆
    episodes = result["episodes"]
    assert any(ep["episode"] == 1 and ep.get("title") == "第一集" for ep in episodes)
    # 重新載入確認持久化
    reloaded = pm.load_project("demo")
    assert any(ep["episode"] == 1 for ep in reloaded.get("episodes", []))


def test_commit_episode_split_existing_episode_updates_in_place(tmp_path):
    from lib.project_manager import ProjectManager
    pm = ProjectManager(projects_root=str(tmp_path / "projects"))
    pm.create_project("demo")
    pm.create_project_metadata("demo", title="t", style="anime", content_mode="narration")
    proj_dir = pm.get_project_path("demo")
    (proj_dir / "source").mkdir(exist_ok=True)
    (proj_dir / "source" / "n.txt").write_text("ab", encoding="utf-8")
    pm.commit_episode_split("demo", "source/n.txt", 1, "a", "b", title="舊標題")
    pm.commit_episode_split("demo", "source/n.txt", 1, "a", "b", title="新標題")
    episodes = pm.load_project("demo").get("episodes", [])
    matching = [ep for ep in episodes if ep["episode"] == 1]
    assert len(matching) == 1
    assert matching[0]["title"] == "新標題"
```

- [ ] **Step 2：跑測試確認失敗**

Run: `uv run python -m pytest tests/test_project_manager_more.py -v -k commit_episode_split`
Expected: FAIL（`AttributeError: ... has no attribute 'commit_episode_split'`）

- [ ] **Step 3：實作 `commit_episode_split`（加在 `lib/project_manager.py` 的 `add_episode` 方法附近）**

```python
    def commit_episode_split(
        self,
        project_name: str,
        source_rel: str,
        episode: int,
        part_before: str,
        part_after: str,
        title: str | None = None,
    ) -> dict:
        """落地一次分集切分：寫 source/episode_{N}.txt（=part_before）與 source/_remaining.txt（=part_after），
        並在 project.json 的 episodes 加/更新 {episode, title?}。原始 source 檔不修改。

        Args:
            source_rel: 來源檔相對路徑（須在 source/ 下），僅用於決定輸出目錄。
        Returns:
            更新後的 project dict。
        """
        project_dir = self.get_project_path(project_name)
        # 路徑安全：source_rel 必須落在 project_dir/source/ 內
        src_abs = (project_dir / source_rel).resolve()
        source_dir = (project_dir / "source").resolve()
        if not src_abs.is_relative_to(source_dir):
            raise ValueError(f"source 路徑超出 source/ 目錄: {source_rel}")
        source_dir.mkdir(parents=True, exist_ok=True)

        (source_dir / f"episode_{episode}.txt").write_text(part_before, encoding="utf-8")
        (source_dir / "_remaining.txt").write_text(part_after, encoding="utf-8")

        project = self.load_project(project_name)
        episodes = project.setdefault("episodes", [])
        existing = next((ep for ep in episodes if int(ep.get("episode", -1)) == int(episode)), None)
        if existing is None:
            existing = {"episode": int(episode)}
            episodes.append(existing)
        if title is not None:
            existing["title"] = title
        episodes.sort(key=lambda ep: int(ep.get("episode", 0)))
        self.save_project(project_name, project)
        logger.info("分集切分落地: episode %d，前半 %d 字元，後半 %d 字元", episode, len(part_before), len(part_after))
        return project
```

- [ ] **Step 4：跑測試確認通過**

Run: `uv run python -m pytest tests/test_project_manager_more.py -v -k commit_episode_split`
Expected: PASS（2 個）

---

### Task 5：`lib/episode_preprocess.py`

**Files:**
- Create: `lib/episode_preprocess.py`
- Test: `tests/test_episode_split_skill.py`（先放這個模組的測試，後面 Task 6/7 再加 handler 測試）

- [ ] **Step 1：寫失敗測試**

```python
# tests/test_episode_split_skill.py
import pytest


def test_run_preprocess_unknown_content_mode_raises(tmp_path):
    from lib.episode_preprocess import run_preprocess
    from lib.project_manager import ProjectManager
    pm = ProjectManager(projects_root=str(tmp_path / "projects"))
    pm.create_project("demo")
    pm.create_project_metadata("demo", title="t", style="anime", content_mode="narration")
    # 把 content_mode 改成不合法值
    proj = pm.load_project("demo")
    proj["content_mode"] = "weird"
    pm.save_project("demo", proj)
    with pytest.raises(ValueError, match="content_mode"):
        run_preprocess(pm.get_project_path("demo"), episode=1)
```

- [ ] **Step 2：跑測試確認失敗**

Run: `uv run python -m pytest tests/test_episode_split_skill.py -v -k run_preprocess`
Expected: FAIL（`ModuleNotFoundError: lib.episode_preprocess`）

- [ ] **Step 3：實作 `lib/episode_preprocess.py`（把 `server/routers/projects.py` 的 `preprocess_episode` 內部 subprocess 邏輯抽出來）**

```python
# lib/episode_preprocess.py
"""Step 1 預處理：依 content_mode 呼叫對應的 skill 腳本（subprocess）。

供 HTTP 路由（server/routers/projects.py）與 gemini/openai function handler 共用。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from lib import agent_profile

# subprocess 逾時（秒）；與既有路由一致
_PREPROCESS_TIMEOUT = 1800

_CONTENT_MODE_SCRIPTS = {
    "narration": ("split_narration_segments.py", "step1_segments.md"),
    "drama": ("normalize_drama_script.py", "step1_normalized_script.md"),
}


def run_preprocess(project_path: Path, episode: int) -> dict:
    """執行某集的 step1 預處理。回 {step1_path, content_mode}。

    Raises:
        ValueError: content_mode 不合法。
        FileNotFoundError: 預處理腳本不存在。
        RuntimeError: 腳本執行失敗（含 stderr 摘要）或逾時。
    """
    import json

    project_json = project_path / "project.json"
    content_mode = "narration"
    if project_json.exists():
        try:
            content_mode = json.loads(project_json.read_text(encoding="utf-8")).get("content_mode", "narration")
        except Exception:
            content_mode = "narration"

    if content_mode not in _CONTENT_MODE_SCRIPTS:
        raise ValueError(f"未知的 content_mode: {content_mode}")
    script_filename, output_filename = _CONTENT_MODE_SCRIPTS[content_mode]

    # repo root：project_path 是 <repo>/projects/<name>，往上兩層
    repo_root = project_path.resolve().parents[1]
    skill_script = agent_profile.skills_root(repo_root) / "generate-script" / "scripts" / script_filename
    if not skill_script.exists():
        raise FileNotFoundError(f"找不到預處理腳本: {skill_script}")

    try:
        proc = subprocess.run(
            [sys.executable, str(skill_script), "--episode", str(episode)],
            cwd=str(project_path),
            capture_output=True,
            text=True,
            timeout=_PREPROCESS_TIMEOUT,
        )
    except subprocess.TimeoutExpired as e:
        raise RuntimeError("預處理執行逾時（>30 分鐘）") from e
    if proc.returncode != 0:
        raise RuntimeError(f"{script_filename} 失敗 (rc={proc.returncode}): {proc.stderr[-2000:]}")

    step1_path = project_path / "drafts" / f"episode_{episode}" / output_filename
    rel = f"drafts/episode_{episode}/{output_filename}" if step1_path.exists() else ""
    return {"step1_path": rel, "content_mode": content_mode}
```

> 註：實作時確認 `agent_profile.skills_root` 接受的是 repo root 而非 `projects/` —— 看 `lib/agent_profile.py` 既有用法（`server/routers/projects.py` 用的是 `agent_profile.skills_root(PROJECT_ROOT)`，`PROJECT_ROOT` 是 repo root）。`project_path.resolve().parents[1]` 應等於 repo root（`<repo>/projects/<name>` → parents[0]=`<repo>/projects`，parents[1]=`<repo>`）。實作時用測試或 `python -c` 確認。

- [ ] **Step 4：跑測試確認通過**

Run: `uv run python -m pytest tests/test_episode_split_skill.py -v -k run_preprocess`
Expected: PASS

- [ ] **Step 5：把 `server/routers/projects.py` 的 `preprocess_episode` 改成呼叫 `lib.episode_preprocess.run_preprocess`**

替換 `preprocess_episode` 函式內部（保留路由裝飾器與簽名、404 檢查、`asyncio.to_thread`、`project_change_source` 不變）：

```python
@router.post("/projects/{name}/episodes/{episode}/preprocess")
async def preprocess_episode(name: str, episode: int, _user: CurrentUser):
    """Step 1 預處理：根據 content_mode 呼叫對應 skill 腳本。"""
    from lib.episode_preprocess import run_preprocess

    try:
        manager = get_project_manager()
        if not manager.project_exists(name):
            raise HTTPException(status_code=404, detail=f"專案 '{name}' 不存在")
        project_path = manager.get_project_path(name)
        with project_change_source("webui"):
            result = await asyncio.to_thread(run_preprocess, project_path, episode)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("請求處理失敗")
        raise HTTPException(status_code=500, detail=str(e))
```

- [ ] **Step 6：跑既有 preprocess 相關測試 + ruff**

Run: `uv run python -m pytest -q -k "preprocess" && uv run ruff check . && uv run ruff format --check .`
Expected: PASS（既有 preprocess 測試不破）；ruff 全綠（若 format 沒過先 `ruff format .`）

---

### Task 6：gemini/openai function handlers — `peek_split_point` + `split_episode` + `preprocess_episode`

**Files:**
- Modify: `server/agent_runtime/skill_function_declarations.py`
- Test: `tests/test_episode_split_skill.py`（追加）

> 背景：`SKILL_DECLARATIONS`（list of FunctionDeclaration）與 `SKILL_HANDLERS`（dict name→handler）是真相源；`adk_tool_adapters.py` 與 `openai_tool_adapters.py` 自動從這兩者建工具。`SkillCallContext` 有 `project_manager`、`project_name`、`project_root`（看既有 handler 怎麼用）。Handler 簽名：`async def _handle_xxx(ctx: SkillCallContext, args: dict[str, Any]) -> dict[str, Any]`。失敗回 `{"ok": False, "error": <code>, "reason": <人話>}`。

- [ ] **Step 1：寫失敗測試（追加到 `tests/test_episode_split_skill.py`）**

```python
import asyncio


def _make_ctx(tmp_path, content_mode="narration"):
    from lib.project_manager import ProjectManager
    from server.agent_runtime.skill_function_declarations import SkillCallContext
    pm = ProjectManager(projects_root=str(tmp_path / "projects"))
    pm.create_project("demo")
    pm.create_project_metadata("demo", title="t", style="anime", content_mode=content_mode)
    proj_dir = pm.get_project_path("demo")
    (proj_dir / "source").mkdir(exist_ok=True)
    # repo_root 引數：看 SkillCallContext 既有欄位名（可能叫 project_root）
    return SkillCallContext(project_manager=pm, project_name="demo", project_root=tmp_path), pm, proj_dir


def test_handle_peek_split_point_success(tmp_path):
    from server.agent_runtime.skill_function_declarations import _handle_peek_split_point
    ctx, pm, proj_dir = _make_ctx(tmp_path)
    (proj_dir / "source" / "n.txt").write_text("甲" * 30 + "。" + "乙" * 30, encoding="utf-8")
    res = asyncio.run(_handle_peek_split_point(ctx, {"source": "source/n.txt", "target_chars": 20}))
    assert res.get("total_chars") == 61
    assert "nearby_breakpoints" in res


def test_handle_peek_split_point_missing_source(tmp_path):
    from server.agent_runtime.skill_function_declarations import _handle_peek_split_point
    ctx, pm, proj_dir = _make_ctx(tmp_path)
    res = asyncio.run(_handle_peek_split_point(ctx, {"source": "source/nope.txt", "target_chars": 5}))
    assert res.get("ok") is False


def test_handle_peek_split_point_path_escape(tmp_path):
    from server.agent_runtime.skill_function_declarations import _handle_peek_split_point
    ctx, pm, proj_dir = _make_ctx(tmp_path)
    res = asyncio.run(_handle_peek_split_point(ctx, {"source": "../../etc/passwd", "target_chars": 5}))
    assert res.get("ok") is False


def test_handle_split_episode_success_and_persisted(tmp_path):
    from server.agent_runtime.skill_function_declarations import _handle_split_episode
    ctx, pm, proj_dir = _make_ctx(tmp_path)
    (proj_dir / "source" / "n.txt").write_text("前半段。他離開了。後半段。", encoding="utf-8")
    res = asyncio.run(_handle_split_episode(ctx, {"source": "source/n.txt", "episode": 1, "target_chars": 5, "anchor": "他離開了。"}))
    assert res.get("ok") is not False
    assert res.get("episode") == 1
    # 寫入後驗證：episode 真的進了 project.json
    assert any(ep["episode"] == 1 for ep in pm.load_project("demo").get("episodes", []))
    assert (proj_dir / "source" / "episode_1.txt").exists()


def test_handle_split_episode_anchor_not_found(tmp_path):
    from server.agent_runtime.skill_function_declarations import _handle_split_episode
    ctx, pm, proj_dir = _make_ctx(tmp_path)
    (proj_dir / "source" / "n.txt").write_text("一些內容。", encoding="utf-8")
    res = asyncio.run(_handle_split_episode(ctx, {"source": "source/n.txt", "episode": 1, "target_chars": 2, "anchor": "不存在"}))
    assert res.get("ok") is False


def test_handle_preprocess_episode_unknown_mode(tmp_path):
    from server.agent_runtime.skill_function_declarations import _handle_preprocess_episode
    ctx, pm, proj_dir = _make_ctx(tmp_path, content_mode="narration")
    proj = pm.load_project("demo"); proj["content_mode"] = "weird"; pm.save_project("demo", proj)
    res = asyncio.run(_handle_preprocess_episode(ctx, {"episode": 1}))
    assert res.get("ok") is False
```

> 註：實作時先確認 `SkillCallContext` 的實際欄位名（grep `class SkillCallContext`），測試裡的 `project_root=tmp_path` 可能要改成正確欄位名。

- [ ] **Step 2：跑測試確認失敗**

Run: `uv run python -m pytest tests/test_episode_split_skill.py -v`
Expected: FAIL（`ImportError: cannot import name '_handle_peek_split_point'`）

- [ ] **Step 3：實作三個 handler + FunctionDeclaration（加到 `skill_function_declarations.py`）**

在現有 handler（如 `_handle_generate_characters`）附近加。先看既有 `FunctionDeclaration` 的構造法（`name` / `description` / `parameters` JSON schema）照抄樣式。

```python
# --- peek_split_point ---
PEEK_SPLIT_POINT_DECL = FunctionDeclaration(
    name="peek_split_point",
    description=(
        "預覽分集切分點（唯讀）。給定 source/ 下的小說檔與目標字數，回該位置前後文與附近自然斷點，"
        "供你決定要在哪個句末/段落切。切完一集後可對 source/_remaining.txt 再 peek 下一集。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "source": {"type": "string", "description": "source/ 下的相對路徑，如 source/novel.txt 或 source/_remaining.txt"},
            "target_chars": {"type": "integer", "description": "目標有效字數（含標點不含空行）"},
            "context": {"type": "integer", "description": "前後文與斷點搜尋視窗，預設 200"},
        },
        "required": ["source", "target_chars"],
    },
)


async def _handle_peek_split_point(ctx: SkillCallContext, args: dict[str, Any]) -> dict[str, Any]:
    from lib import episode_splitter
    source = str(args.get("source") or "").strip()
    target_chars = args.get("target_chars")
    context = args.get("context") or 200
    if not source or not isinstance(target_chars, int):
        return {"ok": False, "error": "invalid_argument", "reason": "需要 source(str) 與 target_chars(int)"}
    project_dir = ctx.project_manager.get_project_path(ctx.project_name)
    src_abs = (project_dir / source).resolve()
    source_dir = (project_dir / "source").resolve()
    if not src_abs.is_relative_to(source_dir):
        return {"ok": False, "error": "path_escape", "reason": f"source 必須在 source/ 下: {source}"}
    if not src_abs.exists():
        return {"ok": False, "error": "not_found", "reason": f"檔案不存在: {source}"}
    try:
        text = src_abs.read_text(encoding="utf-8")
        return episode_splitter.peek_split(text, target_chars, context)
    except ValueError as e:
        return {"ok": False, "error": "invalid_argument", "reason": str(e)}
    except Exception as e:
        return {"ok": False, "error": "peek_failed", "reason": str(e)}


# --- split_episode ---
SPLIT_EPISODE_DECL = FunctionDeclaration(
    name="split_episode",
    description=(
        "執行分集切分：用目標字數縮小範圍、用 anchor（切點前 10~20 字的原文片段）精確定位，"
        "把 source/<檔> 切成 source/episode_{N}.txt（前半）與 source/_remaining.txt（後半），並在 project.json 加 episodes 條目。"
        "原始檔不會被修改。anchor 通常取自 peek_split_point 回傳的某個 nearby_breakpoint 前的文字。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "source": {"type": "string", "description": "source/ 下的相對路徑"},
            "episode": {"type": "integer", "description": "集數編號（1, 2, ...）"},
            "target_chars": {"type": "integer", "description": "與 peek 用的目標字數一致"},
            "anchor": {"type": "string", "description": "切點前的原文片段（10~20 字），用來精確定位切點"},
            "context": {"type": "integer", "description": "anchor 搜尋視窗，預設 500"},
            "title": {"type": "string", "description": "（可選）這一集的標題"},
        },
        "required": ["source", "episode", "target_chars", "anchor"],
    },
)


async def _handle_split_episode(ctx: SkillCallContext, args: dict[str, Any]) -> dict[str, Any]:
    from lib import episode_splitter
    source = str(args.get("source") or "").strip()
    episode = args.get("episode")
    target_chars = args.get("target_chars")
    anchor = str(args.get("anchor") or "")
    context = args.get("context") or 500
    title = args.get("title")
    if not source or not isinstance(episode, int) or not isinstance(target_chars, int) or not anchor:
        return {"ok": False, "error": "invalid_argument", "reason": "需要 source(str), episode(int), target_chars(int), anchor(str)"}
    project_dir = ctx.project_manager.get_project_path(ctx.project_name)
    src_abs = (project_dir / source).resolve()
    source_dir = (project_dir / "source").resolve()
    if not src_abs.is_relative_to(source_dir):
        return {"ok": False, "error": "path_escape", "reason": f"source 必須在 source/ 下: {source}"}
    if not src_abs.exists():
        return {"ok": False, "error": "not_found", "reason": f"檔案不存在: {source}"}
    try:
        text = src_abs.read_text(encoding="utf-8")
        split = episode_splitter.split_episode_text(text, target_chars, anchor, context)
    except ValueError as e:
        return {"ok": False, "error": "split_failed", "reason": str(e)}
    except Exception as e:
        return {"ok": False, "error": "split_failed", "reason": str(e)}
    try:
        ctx.project_manager.commit_episode_split(
            ctx.project_name, source_rel=source, episode=episode,
            part_before=split["part_before"], part_after=split["part_after"], title=title,
        )
    except Exception as e:
        return {"ok": False, "error": "persist_failed", "reason": str(e)}
    # 寫入後驗證
    persisted = ctx.project_manager.load_project(ctx.project_name).get("episodes", [])
    if not any(int(ep.get("episode", -1)) == episode for ep in persisted):
        return {"ok": False, "error": "persist_failed", "reason": f"episode {episode} 未出現在 project.json"}
    return {
        "ok": True,
        "episode": episode,
        "episode_file": f"source/episode_{episode}.txt",
        "remaining_file": "source/_remaining.txt",
        "part_before_chars": len(split["part_before"]),
        "part_after_chars": len(split["part_after"]),
        "split_pos": split["split_pos"],
        "anchor_match_count": split["anchor_match_count"],
    }


# --- preprocess_episode ---
PREPROCESS_EPISODE_DECL = FunctionDeclaration(
    name="preprocess_episode",
    description=(
        "對某一集做 Step 1 預處理（依 content_mode：narration→拆段 / drama→規範化劇本），"
        "產出 drafts/episode_{N}/step1_*.md。生成 JSON 劇本（generate_script）前必須先做這步。"
    ),
    parameters={
        "type": "object",
        "properties": {"episode": {"type": "integer", "description": "集數編號"}},
        "required": ["episode"],
    },
)


async def _handle_preprocess_episode(ctx: SkillCallContext, args: dict[str, Any]) -> dict[str, Any]:
    from lib.episode_preprocess import run_preprocess
    episode = args.get("episode")
    if not isinstance(episode, int):
        return {"ok": False, "error": "invalid_argument", "reason": "需要 episode(int)"}
    project_path = ctx.project_manager.get_project_path(ctx.project_name)
    try:
        result = await asyncio.to_thread(run_preprocess, project_path, episode)
        return {"ok": True, **result}
    except ValueError as e:
        return {"ok": False, "error": "invalid_content_mode", "reason": str(e)}
    except FileNotFoundError as e:
        return {"ok": False, "error": "script_missing", "reason": str(e)}
    except RuntimeError as e:
        return {"ok": False, "error": "preprocess_failed", "reason": str(e)}
    except Exception as e:
        return {"ok": False, "error": "preprocess_failed", "reason": str(e)}
```

然後把這 3 個加進 `SKILL_DECLARATIONS` 與 `SKILL_HANDLERS`：

```python
# SKILL_DECLARATIONS list 末尾加：
    PEEK_SPLIT_POINT_DECL,
    SPLIT_EPISODE_DECL,
    PREPROCESS_EPISODE_DECL,

# SKILL_HANDLERS dict 加：
    "peek_split_point": _handle_peek_split_point,
    "split_episode": _handle_split_episode,
    "preprocess_episode": _handle_preprocess_episode,
```

> 註：若 `asyncio` 尚未在該檔 import，加 `import asyncio`。

- [ ] **Step 4：跑測試確認通過**

Run: `uv run python -m pytest tests/test_episode_split_skill.py -v`
Expected: PASS（全部）

- [ ] **Step 5：跑相關既有測試確認 adapter 自動帶上新工具且沒破**

Run: `uv run python -m pytest -q -k "skill_function or adk_tool or openai_tool or gemini_full or openai_full"`
Expected: PASS（若有測試斷言「工具數量 == 7」之類的需更新成新數量；若有 hard-coded 工具名列表的測試需加上新 3 個）

- [ ] **Step 6：ruff**

```bash
uv run ruff check . && uv run ruff format --check .
```

---

### Task 7：SKILL.md 與 CLAUDE.md 同步

**Files:**
- Modify: `agent_runtime_profile/.claude/skills/manage-project/SKILL.md`
- Modify: `agent_runtime_profile/CLAUDE.md`

- [ ] **Step 1：`manage-project/SKILL.md` — 在「角色/線索批次寫入」段落之後（或「分集切分」相關段落），補一段說明這次新增的 function 能力**

加入（內容大意，措辭依既有風格）：

```markdown
## 分集切分（peek + split）

> 註：以下 `peek_split_point` / `split_episode` / `preprocess_episode` 對 gemini-full / openai-full 是 function，
> 對 Claude 是 `manage-project/scripts/peek_split_point.py` / `split_episode.py` 兩個 CLI 腳本（用法見上）；
> 兩條路徑共用 `lib/episode_splitter.py` 的核心邏輯，行為一致。

流程：
1. `peek_split_point(source="source/novel.txt", target_chars=3000)` → 看目標位置前後文 + nearby_breakpoints
2. 從某個斷點前取 10~20 字當 anchor → `split_episode(source="source/novel.txt", episode=1, target_chars=3000, anchor="...")`
   → 產 source/episode_1.txt（前半）+ source/_remaining.txt（後半），project.json 加 episodes[{episode:1}]
3. 對 source/_remaining.txt 重複 1~2 切下一集（target_chars 從 1 重新算）
4. 對某集 `preprocess_episode(episode=1)` → 產 drafts/episode_1/step1_*.md（生 JSON 劇本前必做）

失敗一律回 `{"ok": false, "error": ..., "reason": ...}`（CLI 腳本則 stderr + 非零結束碼）——看到失敗不可回報完成，依錯誤訊息修正參數重試（最常見：anchor 找不到 → 換成 peek 回傳裡確實存在的片段）。
```

- [ ] **Step 2：`agent_runtime_profile/CLAUDE.md` — 在「關鍵原則」或「project.json 核心欄位」附近加角色/線索提取引導**

加入：

```markdown
### 角色/線索提取

提取角色與線索時：
1. 先用 fs_read 讀 `source/` 下的小說原文（檔案大可分段讀）
2. 自己分析出 characters（name/description/voice_style）與 clues（name/clue_type/description/importance）
3. 呼叫 `generate_characters` / `generate_clues` 寫入 project.json
4. 檢查回傳的 `ok` 欄位——`false` 代表未成功寫入，不可回報「已定義完畢」，需依 `reason` 修正後重試
```

---

## 階段三：HTTP API + 前端

### Task 8：`POST .../episodes/peek` 與 `.../episodes/split` 路由

**Files:**
- Modify: `server/routers/projects.py`
- Test: `tests/test_episode_split_routes.py`

> 看既有路由（如 `generate_episode_script` 約 970 行）的模式：`@router.post(...)`、`asyncio.to_thread(_sync)`、`with project_change_source("webui")`、`get_project_manager()`、`HTTPException`。請求 body 用 Pydantic model（看檔案上方既有 `CreateProjectRequest` 等的定義樣式）。

- [ ] **Step 1：寫失敗測試**

```python
# tests/test_episode_split_routes.py
import pytest
from httpx import ASGITransport, AsyncClient

# 看既有 *_routes.py 測試怎麼取 app / 帶 auth；以下為示意，依既有 fixture 調整
from server.main import app  # 若實際路徑不同，照既有測試改


@pytest.fixture
def client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _setup_project(tmp_path_factory, monkeypatch):
    # 看既有 routes 測試怎麼把 ProjectManager 指到 tmp + 怎麼建專案 + 寫 source 檔
    ...  # 依既有 conftest fixture 實作


async def test_peek_endpoint_success(client, ...):
    # POST /api/v1/projects/{name}/episodes/peek {"source":"source/n.txt","target_chars":20}
    # → 200，body 有 total_chars / nearby_breakpoints
    ...


async def test_peek_endpoint_target_overflow_422(client, ...):
    # target_chars >= 總字數 → 422
    ...


async def test_split_endpoint_success_persisted(client, ...):
    # POST .../episodes/split 成功 → 200，source/episode_1.txt 存在，project.json episodes 有 episode 1
    ...


async def test_split_endpoint_anchor_not_found_400(client, ...):
    # anchor 找不到 → 400
    ...
```

> 註：此 task 的測試骨架需參照 repo 既有 `tests/test_*_routes.py`（如 `tests/test_projects_archive_routes.py`）的 fixture 寫法 — 怎麼 mock ProjectManager 到 tmp、怎麼帶認證、AsyncClient 怎麼建。實作 agent 先讀一個既有 routes 測試檔再照樣寫。

- [ ] **Step 2：跑測試確認失敗**

Run: `uv run python -m pytest tests/test_episode_split_routes.py -v`
Expected: FAIL（路由不存在 → 404）

- [ ] **Step 3：實作路由（加到 `server/routers/projects.py`）**

先在檔案上方 request model 區加：

```python
class PeekSplitRequest(BaseModel):
    source: str
    target_chars: int
    context: int = 200


class SplitEpisodeRequest(BaseModel):
    source: str
    episode: int
    target_chars: int
    anchor: str
    context: int = 500
    title: str | None = None
```

然後加路由（放在 episode 相關路由附近）：

```python
@router.post("/projects/{name}/episodes/peek")
async def peek_episode_split(name: str, req: PeekSplitRequest, _user: CurrentUser):
    """預覽分集切分點（唯讀）。"""
    from lib import episode_splitter

    try:
        manager = get_project_manager()
        if not manager.project_exists(name):
            raise HTTPException(status_code=404, detail=f"專案 '{name}' 不存在")
        project_dir = manager.get_project_path(name)
        src_abs = (project_dir / req.source).resolve()
        source_dir = (project_dir / "source").resolve()
        if not src_abs.is_relative_to(source_dir):
            raise HTTPException(status_code=422, detail=f"source 必須在 source/ 下: {req.source}")
        if not src_abs.exists():
            raise HTTPException(status_code=404, detail=f"檔案不存在: {req.source}")

        def _sync():
            text = src_abs.read_text(encoding="utf-8")
            return episode_splitter.peek_split(text, req.target_chars, req.context)

        return await asyncio.to_thread(_sync)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("請求處理失敗")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{name}/episodes/split")
async def split_episode_route(name: str, req: SplitEpisodeRequest, _user: CurrentUser):
    """執行分集切分：寫 source/episode_{N}.txt + source/_remaining.txt，更新 project.json。"""
    from lib import episode_splitter

    try:
        manager = get_project_manager()
        if not manager.project_exists(name):
            raise HTTPException(status_code=404, detail=f"專案 '{name}' 不存在")
        project_dir = manager.get_project_path(name)
        src_abs = (project_dir / req.source).resolve()
        source_dir = (project_dir / "source").resolve()
        if not src_abs.is_relative_to(source_dir):
            raise HTTPException(status_code=422, detail=f"source 必須在 source/ 下: {req.source}")
        if not src_abs.exists():
            raise HTTPException(status_code=404, detail=f"檔案不存在: {req.source}")

        def _sync():
            text = src_abs.read_text(encoding="utf-8")
            split = episode_splitter.split_episode_text(text, req.target_chars, req.anchor, req.context)
            manager.commit_episode_split(
                name, source_rel=req.source, episode=req.episode,
                part_before=split["part_before"], part_after=split["part_after"], title=req.title,
            )
            persisted = manager.load_project(name).get("episodes", [])
            if not any(int(ep.get("episode", -1)) == req.episode for ep in persisted):
                raise RuntimeError(f"episode {req.episode} 未出現在 project.json")
            return {
                "episode": req.episode,
                "episode_file": f"source/episode_{req.episode}.txt",
                "remaining_file": "source/_remaining.txt",
                "part_before_chars": len(split["part_before"]),
                "part_after_chars": len(split["part_after"]),
                "split_pos": split["split_pos"],
                "anchor_match_count": split["anchor_match_count"],
            }

        with project_change_source("webui"):
            return await asyncio.to_thread(_sync)
    except ValueError as e:
        # anchor 找不到 / target 超界
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("請求處理失敗")
        raise HTTPException(status_code=500, detail=str(e))
```

> 註：`BaseModel` 若該檔尚未 import，加 `from pydantic import BaseModel`（看檔案頂部既有 import）。

- [ ] **Step 4：跑測試確認通過**

Run: `uv run python -m pytest tests/test_episode_split_routes.py -v`
Expected: PASS（全部）

- [ ] **Step 5：ruff**

```bash
uv run ruff check . && uv run ruff format --check .
```

---

### Task 9：前端 `api.ts` 加 method + `EpisodeSplitPanel` 元件

**Files:**
- Modify: `frontend/src/api.ts`
- Create: `frontend/src/components/canvas/timeline/EpisodeSplitPanel.tsx`
- Create: `frontend/src/components/canvas/timeline/EpisodeSplitPanel.test.tsx`
- Modify: `frontend/src/components/canvas/timeline/TimelineCanvas.tsx`

> 前端命令：`cd ~/arcreel360/frontend && export PATH="$HOME/.nvm/versions/node/v22.21.1/bin:$PATH"`，測試 `CI=true COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack pnpm@11.1.0 run test`，typecheck `... corepack pnpm@11.1.0 run typecheck`。

- [ ] **Step 1：寫失敗測試 `EpisodeSplitPanel.test.tsx`**

```tsx
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import { EpisodeSplitPanel } from "./EpisodeSplitPanel";
import { API } from "@/api";

vi.mock("@/api", () => ({
  API: {
    peekEpisodeSplit: vi.fn(),
    splitEpisode: vi.fn(),
  },
}));

const peekResult = {
  total_chars: 100,
  target_chars: 50,
  target_offset: 60,
  context_before: "...前文...",
  context_after: "後文...",
  nearby_breakpoints: [
    { offset: 62, char: "。", type: "sentence", distance: 2 },
    { offset: 70, char: "。", type: "sentence", distance: 10 },
  ],
};

test("peek then split flow", async () => {
  (API.peekEpisodeSplit as any).mockResolvedValue(peekResult);
  (API.splitEpisode as any).mockResolvedValue({ episode: 1, episode_file: "source/episode_1.txt" });
  const onDone = vi.fn();
  render(<EpisodeSplitPanel projectName="demo" sourceFiles={["source/novel.txt"]} onSplitDone={onDone} />);

  // 按「預覽切點」
  fireEvent.click(screen.getByRole("button", { name: /預覽切點/ }));
  await waitFor(() => expect(API.peekEpisodeSplit).toHaveBeenCalled());
  // 顯示了候選斷點
  await screen.findByText(/sentence/);

  // 選第一個斷點 → 按「執行切分」
  fireEvent.click(screen.getAllByRole("button", { name: /選此處/ })[0]);
  fireEvent.click(screen.getByRole("button", { name: /執行切分/ }));
  await waitFor(() => expect(API.splitEpisode).toHaveBeenCalled());
  await waitFor(() => expect(onDone).toHaveBeenCalled());
});

test("shows error when peek fails", async () => {
  (API.peekEpisodeSplit as any).mockRejectedValue(new Error("目標字數超過總字數"));
  render(<EpisodeSplitPanel projectName="demo" sourceFiles={["source/n.txt"]} onSplitDone={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: /預覽切點/ }));
  await screen.findByText(/目標字數超過總字數/);
});
```

- [ ] **Step 2：跑測試確認失敗**

Run: `cd frontend && export PATH="$HOME/.nvm/versions/node/v22.21.1/bin:$PATH" && CI=true COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack pnpm@11.1.0 run test -- EpisodeSplitPanel`
Expected: FAIL（模組不存在）

- [ ] **Step 3：`api.ts` 加 method**

看 `frontend/src/api.ts` 既有 `static async generateEpisodeScript(...)` 的樣式（約 373 行），照樣加：

```typescript
  static async peekEpisodeSplit(
    name: string,
    body: { source: string; target_chars: number; context?: number },
  ): Promise<{
    total_chars: number;
    target_chars: number;
    target_offset: number;
    context_before: string;
    context_after: string;
    nearby_breakpoints: { offset: number; char: string; type: string; distance: number }[];
  }> {
    return this.post(`/projects/${encodeURIComponent(name)}/episodes/peek`, body);
  }

  static async splitEpisode(
    name: string,
    body: { source: string; episode: number; target_chars: number; anchor: string; context?: number; title?: string },
  ): Promise<{
    episode: number;
    episode_file: string;
    remaining_file: string;
    part_before_chars: number;
    part_after_chars: number;
    split_pos: number;
    anchor_match_count: number;
  }> {
    return this.post(`/projects/${encodeURIComponent(name)}/episodes/split`, body);
  }
```

> 註：看既有 `this.post` / `request` helper 的實際名字與簽名照用。回傳型別也可以抽到 `frontend/src/types/` —— 看 repo 慣例（既有 API method 是 inline 還是用 types）。

- [ ] **Step 4：實作 `EpisodeSplitPanel.tsx`**

最小可用版本（樣式抄 `EpisodeActionsBar.tsx` 的 Tailwind class 風格）：

```tsx
import { useState } from "react";
import { Scissors } from "lucide-react";
import { API } from "@/api";
import { useAppStore } from "@/stores/app-store";

interface PeekResult {
  total_chars: number;
  target_chars: number;
  target_offset: number;
  context_before: string;
  context_after: string;
  nearby_breakpoints: { offset: number; char: string; type: string; distance: number }[];
}

interface Props {
  projectName: string;
  sourceFiles: string[]; // source/ 下的 .txt 檔（含 _remaining.txt）
  onSplitDone: () => void; // 切分成功後（呼叫方重新載入專案）
}

export function EpisodeSplitPanel({ projectName, sourceFiles, onSplitDone }: Props) {
  const [source, setSource] = useState(sourceFiles[0] ?? "");
  const [targetChars, setTargetChars] = useState(3000);
  const [episode, setEpisode] = useState(1);
  const [peek, setPeek] = useState<PeekResult | null>(null);
  const [anchor, setAnchor] = useState("");
  const [busy, setBusy] = useState<"peek" | "split" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const toast = (m: string, k: "success" | "error" = "success") => useAppStore.getState().pushToast(m, k);

  const doPeek = async () => {
    setBusy("peek"); setError(null);
    try {
      const r = await API.peekEpisodeSplit(projectName, { source, target_chars: targetChars });
      setPeek(r);
    } catch (e) {
      setError((e as Error).message);
    } finally { setBusy(null); }
  };

  const pickBreakpoint = (offset: number) => {
    if (!peek) return;
    // 取斷點前 16 字當 anchor（從 context_before 尾端粗略取；精確 anchor 由使用者可再編輯）
    const approx = peek.context_before.slice(-16);
    setAnchor(approx);
  };

  const doSplit = async () => {
    setBusy("split"); setError(null);
    try {
      await API.splitEpisode(projectName, { source, episode, target_chars: targetChars, anchor });
      toast(`已切出第 ${episode} 集`);
      onSplitDone();
      setPeek(null); setAnchor("");
    } catch (e) {
      setError((e as Error).message);
    } finally { setBusy(null); }
  };

  return (
    <div className="rounded-lg border border-gray-700 bg-gray-900/50 p-4">
      <div className="mb-3 flex items-center gap-2 text-sm text-gray-300">
        <Scissors className="h-4 w-4" /> 分集切分
      </div>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <select value={source} onChange={(e) => setSource(e.target.value)} className="rounded border border-gray-700 bg-gray-800 px-2 py-1 text-gray-200">
          {sourceFiles.map((f) => <option key={f} value={f}>{f}</option>)}
        </select>
        <label className="text-gray-400">目標字數</label>
        <input type="number" value={targetChars} onChange={(e) => setTargetChars(Number(e.target.value))} className="w-24 rounded border border-gray-700 bg-gray-800 px-2 py-1 text-gray-200" />
        <label className="text-gray-400">集數</label>
        <input type="number" value={episode} onChange={(e) => setEpisode(Number(e.target.value))} className="w-16 rounded border border-gray-700 bg-gray-800 px-2 py-1 text-gray-200" />
        <button type="button" onClick={() => void doPeek()} disabled={busy !== null} className="rounded-lg border border-gray-700 px-2.5 py-1 text-gray-300 hover:border-gray-500 disabled:opacity-50">預覽切點</button>
      </div>
      {error && <p className="mt-2 text-xs text-red-400">{error}</p>}
      {peek && (
        <div className="mt-3 text-xs text-gray-300">
          <p className="text-gray-500">總字數 {peek.total_chars}，目標位置 offset {peek.target_offset}</p>
          <p className="mt-1 whitespace-pre-wrap rounded bg-gray-800 p-2 text-gray-400">…{peek.context_before}<span className="text-amber-400">▮</span>{peek.context_after}…</p>
          <p className="mt-2 text-gray-500">附近斷點：</p>
          <ul className="mt-1 space-y-1">
            {peek.nearby_breakpoints.map((bp, i) => (
              <li key={i} className="flex items-center gap-2">
                <span className="text-gray-400">{bp.type} @ {bp.offset}（距 {bp.distance}）</span>
                <button type="button" onClick={() => pickBreakpoint(bp.offset)} className="rounded border border-gray-700 px-1.5 py-0.5 text-gray-300 hover:border-gray-500">選此處</button>
              </li>
            ))}
          </ul>
          <div className="mt-2 flex items-center gap-2">
            <label className="text-gray-400">切點前文字（anchor）</label>
            <input value={anchor} onChange={(e) => setAnchor(e.target.value)} className="flex-1 rounded border border-gray-700 bg-gray-800 px-2 py-1 text-gray-200" placeholder="10~20 字的原文片段" />
            <button type="button" onClick={() => void doSplit()} disabled={busy !== null || !anchor} className="rounded-lg border border-emerald-500/40 px-2.5 py-1 text-emerald-300 hover:border-emerald-400 disabled:opacity-50">執行切分</button>
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 5：跑測試確認通過**

Run: `cd frontend && export PATH="$HOME/.nvm/versions/node/v22.21.1/bin:$PATH" && CI=true COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack pnpm@11.1.0 run test -- EpisodeSplitPanel`
Expected: PASS（2 個測試）

- [ ] **Step 6：在 `TimelineCanvas.tsx` 掛載**

看 `TimelineCanvas.tsx` 怎麼拿到專案資料（`episodes`、source 檔列表）。在「episodes 為空且 source/ 有 .txt 檔」時渲染 `<EpisodeSplitPanel projectName={...} sourceFiles={...} onSplitDone={() => /* 重新載入專案 */} />`。`onSplitDone` 接到既有「重新載入專案」的機制（看 `TimelineCanvas` 既有怎麼 refetch）。

> 註：source 檔列表從哪來——看 `asset_fingerprints` 或既有專案檔案列表 API（`compute_asset_fingerprints` / `/files` 之類）。實作 agent 視 `TimelineCanvas` 現有資料決定，若 `source/` 列表不容易拿到，可先簡化為「讓使用者手填 source 路徑（預設 source/novel.txt）」並在後續迭代補下拉。

- [ ] **Step 7：typecheck + 全部前端測試**

Run: `cd frontend && export PATH="$HOME/.nvm/versions/node/v22.21.1/bin:$PATH" && CI=true COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack pnpm@11.1.0 run typecheck && CI=true COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack pnpm@11.1.0 run test`
Expected: typecheck exit 0；測試全綠

---

## 階段四：整體驗收

### Task 10：全套測試 + lint + 回歸檢查

- [ ] **Step 1：後端全套**

Run: `uv run ruff check . && uv run ruff format --check . && uv run python -m pytest -q`
Expected: ruff 全綠；pytest 全綠（覆蓋率 ≥80%；既有的 asyncio teardown warnings 可忽略）

- [ ] **Step 2：前端全套**

Run: `cd frontend && export PATH="$HOME/.nvm/versions/node/v22.21.1/bin:$PATH" && CI=true COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack pnpm@11.1.0 run typecheck && CI=true COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack pnpm@11.1.0 run test`
Expected: typecheck exit 0；測試全綠

- [ ] **Step 3：Claude CLI 腳本回歸（再驗一次）**

Run: 重跑 Task 3 Step 4 的 diff 比對
Expected: peek / split 腳本 stdout 與改 wrapper 前逐字一致

- [ ] **Step 4：手動 sanity（可選）**

用 `smoketest-gemini-full` 專案：放一個 `source/test_novel.txt`（隨便貼幾千字），跑 `POST /api/v1/projects/smoketest-gemini-full/episodes/peek` 與 `.../split`，確認 `source/episode_1.txt`、`source/_remaining.txt` 產生、`project.json` episodes 多一筆、工作區出現第 1 集 tab。

- [ ] **Step 5：把設計文件狀態改 Done（待使用者確認後）**

設計文件 `docs/superpowers/specs/2026-05-12-非claude-provider-工作流對齊-design.md` 的「狀態：Draft」→「狀態：Done」**僅在使用者明確確認完成後**才改（repo 規範：plan/spec 狀態由使用者確認）。

```bash
git add docs/superpowers/specs/2026-05-12-非claude-provider-工作流對齊-design.md
git commit -m "docs: 設計文件標記完成"
```

---

## 自審結果

- **Spec 覆蓋**：lib/episode_splitter（Task 1-2）、CLI wrapper（Task 3）、commit_episode_split（Task 4）、lib/episode_preprocess（Task 5）、3 個 function handler（Task 6）、SKILL.md/CLAUDE.md 同步（Task 7）、HTTP API（Task 8）、前端（Task 9）、驗收（Task 10）—— spec 各節都對應到 task。「角色提取靠 prompt」→ Task 7 Step 2。「ProjectManager 不拆」→ 已在檔案結構區固定為決策（spec 允許的逃生口）。
- **Placeholder 掃描**：Task 8 的測試骨架標註「依既有 routes 測試 fixture 實作」—— 這是因為 repo 的測試 fixture 寫法只有讀既有檔才知道，屬於合理的「先讀再寫」指示而非偷懶；其餘 step 都有完整程式碼。Task 9 Step 6 的「source 檔列表從哪來」同理（依 TimelineCanvas 現狀），並給了簡化 fallback。
- **型別/命名一致性**：`peek_split` 回傳 key（`context_before` / `context_after` / `nearby_breakpoints`）在 lib（Task 2）、handler（Task 6）、HTTP（Task 8）、前端型別（Task 9）一致。`split_episode_text` 回傳 key（`part_before` / `part_after` / `split_pos` / `before_preview` / `after_preview` / `anchor_match_count` / `target_offset`）在 Task 2 定義，Task 4/6/8 使用一致。`commit_episode_split(project_name, source_rel, episode, part_before, part_after, title)` 簽名在 Task 4 定義，Task 6/8 呼叫一致。
