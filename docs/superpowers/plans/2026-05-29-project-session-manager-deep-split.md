# ProjectManager 與 SessionManager 深度分層拆分計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**狀態:** Draft（依使用者全域規範，未經使用者明確確認前不標 Done）

**Goal:** 把 `lib/project_manager.py`(1489 行)與 `server/agent_runtime/session_manager.py`(1694 行）兩個「上帝物件」按真實職責邊界拆成多個聚焦模組，核心類降到 ~500 / ~800 行，且對外公開簽名零破壞。

**Architecture:** 採「機制 vs 策略」分離 + 委派模式。把持久化、路徑解析、process 控制、prompt 拼接等「技術關注點」抽成獨立模組，核心類保留公開方法簽名並轉發給內部 collaborator。延續先前 lorebook/episode 子域拆分的同一 pattern，但這次拆的是技術關注點而非資料子域。

**Tech Stack:** Python 3.13、FastAPI、SQLAlchemy async、claude-agent-sdk、pytest（asyncio_mode=auto）、ruff。

---

## 設計原則與不變量（執行前必讀）

1. **公開簽名零破壞**：`ProjectManager` / `SessionManager` 的所有 public 方法簽名、回傳型別不得改變。呼叫端遍佈 `server/routers/`、`server/services/`、`server/agent_runtime/`，本計畫**不修改任何呼叫端**。
2. **委派而非搬移 public 方法**：public 方法留在原類，body 改為一行轉發 `return self._collaborator.method(...)`。
3. **每個 Task 結束時測試必須全綠**：基準是 `1673 passed`（拆分前實測）。任何 Task 後出現 fail 即代表該 Task 破壞了行為等價，必須停止並修復。
4. **每個 Task 一個 commit**：commit 後該模組可獨立 import、測試通過。
5. **TDD 適用於新抽出的純模組**：對無狀態工具模組（paths、process control）先寫測試確立契約，再搬實作。對委派改寫（既有行為已被現存測試覆蓋）則以「跑現有測試確認等價」代替新寫測試。

### 已核實的耦合事實（影響拆法，勿憑方法名臆測）

| 方法 | 實際依賴 | 結論 |
|---|---|---|
| `get_*_path`、`_safe_subpath` | 僅 `self.projects_root` / `get_project_path` | ✅ 可抽純模組 |
| `_atomic_write_json` | static，無 self | ✅ 可抽純函式 |
| `_project_lock` | `_get_project_file_path` | ✅ 可隨 store 一起抽 |
| `get_scenes_needing_storyboard` | `load_script`（script 域，**非** path 域） | ⚠️ 歸 script_repository，不歸 paths |
| `normalize_script` 群 | `create_generated_assets`/`create_scene_template`/`normalize_scene`/`load/save_script`/`update_scene_status` + `sync_*_from_script`(lorebook) | ⚠️ 高內聚閉環，整組一起抽；`sync_*` 維持委派 lorebook |
| `generate_overview` | `load_project`/`save_project`/`_read_source_files` | ⚠️ 需 store；`_read_source_files` 移入 overview_generator |
| `_build_options`(session) | `_build_append_prompt`/`data_dir`/`_is_path_allowed`/`_keep_stream_open_hook`/`max_turns`/`_resolve_project_cwd` | ⚠️ **耦合深，不能抽純函式**，保留在類內，僅把 `_build_append_prompt`/`_build_project_context`/`_append_overview_section` 抽成傳入依賴的 builder |
| `_is_path_allowed`(session) | `self.project_root`/`_encode_sdk_project_path` | ⚠️ 抽到 hooks 時須連 `_encode_sdk_project_path` 一起帶 |
| `_get_client_process`/`_process_pid`/`_process_returncode` | static | ✅ 可抽純模組 |
| `_wait_for_process_exit`/`_force_close_client_process` | `self._process_returncode`/`self._wait_for_process_exit` | ⚠️ 非 static，但只依賴同群 process helper，可整組抽成模組函式 |

---

## File Structure

### ProjectManager 拆分後

| 檔案 | 職責 | 行數預估 |
|---|---|---|
| `lib/project_paths.py`（新） | 無狀態路徑解析：所有 `get_*_path`、`_safe_subpath`、`normalize_project_name`、`_slugify_project_title`、`_get_project_file_path` | ~120 |
| `lib/project_store.py`（新） | JSON 持久化引擎：`load/save_project`、`_atomic_write_json`、`_project_lock`、`_touch_metadata`、`update_project`、`project_exists`、`create_project_metadata` | ~250 |
| `lib/script_repository.py`（新） | 劇本/場景領域邏輯：`create/save/load/list_script`、`normalize_script`、`normalize_scene`、`update_scene_status`、`add_scene`、`update_scene_asset/backend`、`get_pending_scenes`、`get_scenes_needing_storyboard`、`sync_episode_from_script`、`create_generated_assets`、`create_scene_template`、`_scene_entry` | ~600 |
| `lib/symlink_repair.py`（新） | `repair_claude_symlink`、`repair_all_symlinks` | ~70 |
| `lib/overview_generator.py`（既有，擴充） | 新增 `_read_source_files`；`generate_overview` 邏輯主體移入，PM 委派 | +50 |
| `lib/project_manager.py`（瘦身） | 門面 + collaborator 組裝 + `get_project_status`/`sync_project_status`（跨域聚合）+ 既有 lorebook/episode 委派 | ~450 |

### SessionManager 拆分後

| 檔案 | 職責 | 行數預估 |
|---|---|---|
| `server/agent_runtime/managed_session.py`（新） | `ManagedSession` dataclass + `PendingQuestion` + `SessionCapacityError`：message buffer、訂閱廣播、queue 驅逐、pending question | ~180 |
| `server/agent_runtime/session_prompt_builder.py`（新） | `build_append_prompt`、`build_project_context`、`append_overview_section`：純函式，依賴以參數傳入 | ~120 |
| `server/agent_runtime/sdk_process_control.py`（新） | `get_client_process`、`process_pid`、`process_returncode`、`wait_for_process_exit`、`force_close_client_process`、`cancel_task`：模組級函式 | ~150 |
| `server/agent_runtime/session_hooks.py`（既有，擴充） | 新增 `is_path_allowed`、`encode_sdk_project_path`、`build_can_use_tool_callback`、`handle_ask_user_question` | +200 |
| `server/agent_runtime/session_manager.py`（瘦身） | 核心 orchestration：`send_new_session`、`get_or_connect`、`send_message`、`_consume_messages`、`_disconnect_session*`、patrol、capacity、`_build_options`（保留，耦合深） | ~800 |

---

## ProjectManager 拆分

### Task 1: 抽出 `project_paths.py`（無狀態路徑解析）

**Files:**
- Create: `lib/project_paths.py`
- Create: `tests/test_project_paths.py`
- Modify: `lib/project_manager.py`

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_project_paths.py
from pathlib import Path

from lib.project_paths import ProjectPaths


def test_get_project_path_under_root():
    paths = ProjectPaths(Path("/tmp/projects"))
    assert paths.get_project_path("demo") == Path("/tmp/projects/demo")


def test_subpaths_compose_correctly():
    paths = ProjectPaths(Path("/tmp/projects"))
    assert paths.get_source_path("demo", "a.txt") == Path("/tmp/projects/demo/source/a.txt")
    assert paths.get_storyboard_path("demo", "s.png") == Path("/tmp/projects/demo/storyboards/s.png")
    assert paths.get_video_path("demo", "v.mp4") == Path("/tmp/projects/demo/videos/v.mp4")


def test_normalize_project_name_strips_unsafe():
    assert ProjectPaths.normalize_project_name("../evil") != "../evil"


def test_safe_subpath_rejects_traversal():
    paths = ProjectPaths(Path("/tmp/projects"))
    import pytest
    with pytest.raises(ValueError):
        paths._safe_subpath(Path("/tmp/projects/demo"), "../../etc/passwd")
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run python -m pytest tests/test_project_paths.py -v`
Expected: FAIL（`ModuleNotFoundError: lib.project_paths`）

- [ ] **Step 3: 建立 `ProjectPaths`**

把 `project_manager.py` 中以下方法的**實作原樣搬入**（不改邏輯）：`normalize_project_name`(static)、`_slugify_project_title`(static)、`get_project_path`、`_safe_subpath`(static)、`get_source_path`、`get_character_path`、`get_storyboard_path`、`get_video_path`、`get_output_path`、`get_scene_path`、`get_clue_path`、`get_storyboard_path`、`_get_project_file_path`。

```python
# lib/project_paths.py
from pathlib import Path


class ProjectPaths:
    """無狀態的專案路徑解析器：僅依賴 projects_root。"""

    def __init__(self, projects_root: Path):
        self.projects_root = projects_root

    @staticmethod
    def normalize_project_name(name: str) -> str:
        ...  # 從 project_manager.py:104 原樣搬入

    @staticmethod
    def _slugify_project_title(title: str) -> str:
        ...  # 從 project_manager.py:114 原樣搬入

    def get_project_path(self, name: str) -> Path:
        ...  # 從 project_manager.py:266 原樣搬入（self.projects_root 不變）

    @staticmethod
    def _safe_subpath(base_dir: Path, filename: str) -> str:
        ...  # 從 project_manager.py:279 原樣搬入

    def _get_project_file_path(self, project_name: str) -> Path:
        ...  # 從 project_manager.py:982 原樣搬入

    def get_source_path(self, project_name: str, filename: str) -> Path:
        return self.get_project_path(project_name) / "source" / filename

    def get_character_path(self, project_name: str, filename: str) -> Path:
        return self.get_project_path(project_name) / "characters" / filename

    def get_storyboard_path(self, project_name: str, filename: str) -> Path:
        return self.get_project_path(project_name) / "storyboards" / filename

    def get_video_path(self, project_name: str, filename: str) -> Path:
        return self.get_project_path(project_name) / "videos" / filename

    def get_output_path(self, project_name: str, filename: str) -> Path:
        return self.get_project_path(project_name) / "output" / filename

    def get_scene_path(self, project_name: str, filename: str) -> Path:
        ...  # 從 project_manager.py:1350 原樣搬入

    def get_clue_path(self, project_name: str, filename: str) -> Path:
        ...  # 從 project_manager.py:1302 原樣搬入
```

- [ ] **Step 4: 跑測試確認通過**

Run: `uv run python -m pytest tests/test_project_paths.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: `ProjectManager` 委派路徑方法**

在 `ProjectManager.__init__` 加入 `self._paths = ProjectPaths(self.projects_root)`（`projects_root` 須為 `Path`，若原為 str 用 `Path(...)` 包裝）。把上述每個 public 路徑方法 body 改為一行委派，例如：

```python
def get_source_path(self, project_name: str, filename: str) -> Path:
    return self._paths.get_source_path(project_name, filename)

@staticmethod
def normalize_project_name(name: str) -> str:
    return ProjectPaths.normalize_project_name(name)
```

`get_project_path` / `_get_project_file_path` / `_safe_subpath` 同樣改委派。`import` 加上 `from lib.project_paths import ProjectPaths`。

- [ ] **Step 6: 跑全套測試確認等價**

Run: `uv run python -m pytest tests/ -q`
Expected: `1673 passed`（或 ≥ 基準，不得有新 fail）

- [ ] **Step 7: lint + commit**

```bash
uv run ruff check --fix lib/project_paths.py lib/project_manager.py tests/test_project_paths.py
uv run ruff format lib/project_paths.py lib/project_manager.py tests/test_project_paths.py
git add lib/project_paths.py lib/project_manager.py tests/test_project_paths.py
git commit -m "refactor(lib): 抽出 ProjectPaths 路徑解析模組"
```

---

### Task 2: 抽出 `project_store.py`（JSON 持久化引擎）

**Files:**
- Create: `lib/project_store.py`
- Create: `tests/test_project_store.py`
- Modify: `lib/project_manager.py`

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_project_store.py
from pathlib import Path

import pytest

from lib.project_paths import ProjectPaths
from lib.project_store import ProjectStore


@pytest.fixture
def store(tmp_path: Path) -> ProjectStore:
    root = tmp_path / "projects"
    root.mkdir()
    (root / "demo").mkdir()
    return ProjectStore(ProjectPaths(root))


def test_save_then_load_roundtrip(store: ProjectStore):
    store.save_project("demo", {"name": "demo", "episodes": []})
    loaded = store.load_project("demo")
    assert loaded["name"] == "demo"


def test_atomic_write_does_not_leave_tmp(store: ProjectStore, tmp_path: Path):
    store.save_project("demo", {"name": "demo"})
    leftovers = list((tmp_path / "projects" / "demo").glob(".project.*.tmp"))
    assert leftovers == []


def test_update_project_is_immutable_merge(store: ProjectStore):
    store.save_project("demo", {"name": "demo", "title": "old"})
    store.update_project("demo", {"title": "new"})
    assert store.load_project("demo")["title"] == "new"
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run python -m pytest tests/test_project_store.py -v`
Expected: FAIL（`ModuleNotFoundError: lib.project_store`）

- [ ] **Step 3: 建立 `ProjectStore`**

接受一個 `ProjectPaths` 注入。原樣搬入：`load_project`、`save_project`、`_atomic_write_json`(static)、`_project_lock`、`_touch_metadata`(static)、`update_project`、`project_exists`、`create_project_metadata`。`_project_lock` / `save_project` 內部呼叫的 `_get_project_file_path` 改為 `self._paths._get_project_file_path`。

```python
# lib/project_store.py
import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from lib.project_paths import ProjectPaths


class ProjectStore:
    """專案 JSON 的持久化引擎：原子寫、檔案鎖、metadata。"""

    def __init__(self, paths: ProjectPaths):
        self._paths = paths

    def load_project(self, project_name: str) -> dict:
        ...  # 從 project_manager.py:993 原樣搬入，self._get_project_file_path → self._paths._get_project_file_path

    @contextmanager
    def _project_lock(self, project_name: str):
        lock_path = self._paths._get_project_file_path(project_name).with_suffix(".lock")
        ...  # 其餘從 project_manager.py:1012 原樣搬入

    @staticmethod
    def _atomic_write_json(path: Path, data: dict) -> None:
        ...  # 從 project_manager.py:1029 原樣搬入

    def save_project(self, project_name: str, project: dict) -> Path:
        ...  # 從 project_manager.py:1052 原樣搬入

    def update_project(self, project_name: str, updates: dict[str, Any]) -> dict:
        ...  # 從 project_manager.py:1077 原樣搬入

    @staticmethod
    def _touch_metadata(project: dict) -> None:
        ...  # 從 project_manager.py:1107 原樣搬入

    def project_exists(self, project_name: str) -> bool:
        ...  # 從 project_manager.py:986 原樣搬入

    def create_project_metadata(self, *args, **kwargs):
        ...  # 從 project_manager.py:1114 原樣搬入（保持原簽名）
```

- [ ] **Step 4: 跑測試確認通過**

Run: `uv run python -m pytest tests/test_project_store.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: `ProjectManager` 委派持久化方法**

`__init__` 加 `self._store = ProjectStore(self._paths)`。把 `load_project`/`save_project`/`update_project`/`project_exists`/`create_project_metadata`/`_project_lock`/`_get_project_file_path`（若仍被內部用到則保留委派）改為委派 `self._store`。`_atomic_write_json`/`_touch_metadata` 若無外部呼叫者可直接移除原副本，改由 store 持有。

```python
def load_project(self, project_name: str) -> dict:
    return self._store.load_project(project_name)

def save_project(self, project_name: str, project: dict) -> Path:
    return self._store.save_project(project_name, project)
```

- [ ] **Step 6: 跑全套測試確認等價**

Run: `uv run python -m pytest tests/ -q`
Expected: `1673 passed`（不得有新 fail；特別注意 concurrency / lock 相關測試）

- [ ] **Step 7: lint + commit**

```bash
uv run ruff check --fix lib/project_store.py lib/project_manager.py tests/test_project_store.py
uv run ruff format lib/project_store.py lib/project_manager.py tests/test_project_store.py
git add lib/project_store.py lib/project_manager.py tests/test_project_store.py
git commit -m "refactor(lib): 抽出 ProjectStore JSON 持久化引擎"
```

---

### Task 3: 抽出 `script_repository.py`（劇本/場景領域邏輯）

**Files:**
- Create: `lib/script_repository.py`
- Create: `tests/test_script_repository.py`
- Modify: `lib/project_manager.py`

> **耦合注意**：此群是高內聚閉環，依賴 `ProjectStore`（load/save）、`ProjectPaths`，並透過回呼委派 `sync_characters_from_script`/`sync_clues_from_script`（屬 lorebook 域）。`ScriptRepository` 建構時注入 `store`、`paths`，並接受兩個 `sync` callable 以避免反向依賴 lorebook。

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_script_repository.py
from pathlib import Path

import pytest

from lib.project_paths import ProjectPaths
from lib.project_store import ProjectStore
from lib.script_repository import ScriptRepository


@pytest.fixture
def repo(tmp_path: Path) -> ScriptRepository:
    root = tmp_path / "projects"
    (root / "demo" / "scripts").mkdir(parents=True)
    paths = ProjectPaths(root)
    store = ProjectStore(paths)
    return ScriptRepository(paths=paths, store=store, sync_characters=lambda *a: None, sync_clues=lambda *a: None)


def test_create_and_load_script(repo: ScriptRepository):
    repo.create_script("demo", title="T", chapter="C1")
    scripts = repo.list_scripts("demo")
    assert len(scripts) == 1


def test_get_scenes_needing_storyboard_filters_done(repo: ScriptRepository):
    repo.save_script("demo", {"content_mode": "narration", "segments": [
        {"id": "s1", "generated_assets": {"storyboard_image": "x.png"}},
        {"id": "s2", "generated_assets": {}},
    ]}, "ep1.json")
    pending = repo.get_scenes_needing_storyboard("demo", "ep1.json")
    assert [s["id"] for s in pending] == ["s2"]
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run python -m pytest tests/test_script_repository.py -v`
Expected: FAIL（`ModuleNotFoundError: lib.script_repository`）

- [ ] **Step 3: 建立 `ScriptRepository`**

原樣搬入：`create_script`、`save_script`、`load_script`、`list_scripts`、`sync_episode_from_script`、`update_character_sheet`、`create_generated_assets`(static)、`create_scene_template`(static)、`normalize_scene`、`update_scene_status`、`normalize_script`、`add_scene`、`update_scene_asset`、`update_scene_backend`、`get_pending_scenes`、`get_scenes_needing_storyboard`、`_scene_entry`(static)、`_needs_generated_sheet`(static)、`_apply_scene_backend`(模組函式)、`_find_script_filename_by_scene_id`、storyboard sheet 相關（`update_storyboard_*`、`_update_storyboard_item_field`）。

`normalize_script` 內對 `self.sync_characters_from_script` / `self.sync_clues_from_script` 的呼叫改為注入的 callable：`self._sync_characters(project_name, script_filename)`。

```python
# lib/script_repository.py
from pathlib import Path
from typing import Any, Callable

from lib.project_paths import ProjectPaths
from lib.project_store import ProjectStore


class ScriptRepository:
    """劇本與場景的領域邏輯：CRUD、正規化、場景狀態。"""

    def __init__(
        self,
        *,
        paths: ProjectPaths,
        store: ProjectStore,
        sync_characters: Callable[[str, str], Any],
        sync_clues: Callable[[str, str], Any],
    ):
        self._paths = paths
        self._store = store
        self._sync_characters = sync_characters
        self._sync_clues = sync_clues

    # ... 上列方法原樣搬入，self.load_project→self._store.load_project，
    #     self.get_*_path→self._paths.get_*_path，
    #     self.sync_characters_from_script→self._sync_characters
```

- [ ] **Step 4: 跑測試確認通過**

Run: `uv run python -m pytest tests/test_script_repository.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: `ProjectManager` 委派劇本方法**

`__init__` 加：

```python
self._scripts = ScriptRepository(
    paths=self._paths,
    store=self._store,
    sync_characters=self.sync_characters_from_script,
    sync_clues=self.sync_clues_from_script,
)
```

把上列每個 public 方法改委派 `self._scripts.xxx(...)`。

- [ ] **Step 6: 跑全套測試確認等價**

Run: `uv run python -m pytest tests/ -q`
Expected: `1673 passed`

- [ ] **Step 7: lint + commit**

```bash
uv run ruff check --fix lib/script_repository.py lib/project_manager.py tests/test_script_repository.py
uv run ruff format lib/script_repository.py lib/project_manager.py tests/test_script_repository.py
git add lib/script_repository.py lib/project_manager.py tests/test_script_repository.py
git commit -m "refactor(lib): 抽出 ScriptRepository 劇本場景領域層"
```

---

### Task 4: 抽出 `symlink_repair.py` 並把 `_read_source_files` 移入 `overview_generator.py`

**Files:**
- Create: `lib/symlink_repair.py`
- Modify: `lib/overview_generator.py`
- Modify: `lib/project_manager.py`
- Create: `tests/test_symlink_repair.py`

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_symlink_repair.py
from pathlib import Path

from lib.symlink_repair import repair_claude_symlink


def test_repair_creates_symlink_when_missing(tmp_path: Path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    result = repair_claude_symlink(project_dir)
    assert "status" in result
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run python -m pytest tests/test_symlink_repair.py -v`
Expected: FAIL（`ModuleNotFoundError: lib.symlink_repair`）

- [ ] **Step 3: 搬移實作**

把 `repair_claude_symlink`、`repair_all_symlinks` 從 PM 搬成 `symlink_repair.py` 的模組級函式（原為 method，把 `self` 相關改為參數，例如 `repair_all_symlinks(projects_root, list_projects)` 或直接接受 `paths`）。把 `_read_source_files` 搬入 `overview_generator.py`，並把 `generate_overview` 主體邏輯移入 overview_generator 的一個 async 函式 `generate_overview(store, project_name)`，PM 委派。

```python
# lib/symlink_repair.py
from pathlib import Path


def repair_claude_symlink(project_dir: Path) -> dict:
    ...  # 從 project_manager.py:205 搬入，self 改參數

def repair_all_symlinks(projects_root: Path, project_names: list[str]) -> dict:
    ...  # 從 project_manager.py:245 搬入
```

```python
# lib/overview_generator.py（擴充）
def _read_source_files(paths, project_name: str, max_chars: int = 50000) -> str:
    ...  # 從 project_manager.py:1406 搬入

async def generate_overview(store, paths, project_name: str) -> dict:
    project = store.load_project(project_name)
    source_text = _read_source_files(paths, project_name)
    ...  # 從 project_manager.py:1444 搬入主體；save 用 store.save_project
```

- [ ] **Step 4: 跑測試確認通過**

Run: `uv run python -m pytest tests/test_symlink_repair.py -v`
Expected: PASS（1 passed）

- [ ] **Step 5: `ProjectManager` 委派**

```python
def repair_claude_symlink(self, project_dir: Path) -> dict:
    return repair_claude_symlink(project_dir)

def repair_all_symlinks(self) -> dict:
    return repair_all_symlinks(self.projects_root, self.list_projects())

async def generate_overview(self, project_name: str) -> dict:
    return await overview_generator.generate_overview(self._store, self._paths, project_name)
```

- [ ] **Step 6: 跑全套測試確認等價**

Run: `uv run python -m pytest tests/ -q`
Expected: `1673 passed`

- [ ] **Step 7: lint + commit**

```bash
uv run ruff check --fix lib/symlink_repair.py lib/overview_generator.py lib/project_manager.py tests/test_symlink_repair.py
uv run ruff format lib/symlink_repair.py lib/overview_generator.py lib/project_manager.py tests/test_symlink_repair.py
git add lib/symlink_repair.py lib/overview_generator.py lib/project_manager.py tests/test_symlink_repair.py
git commit -m "refactor(lib): 抽出 symlink_repair 與 overview 來源讀取"
```

---

## SessionManager 拆分

### Task 5: 抽出 `managed_session.py`（最乾淨的一刀）

**Files:**
- Create: `server/agent_runtime/managed_session.py`
- Modify: `server/agent_runtime/session_manager.py`
- Create: `tests/test_managed_session.py`

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_managed_session.py
import asyncio

import pytest

from server.agent_runtime.managed_session import ManagedSession, PendingQuestion, SessionCapacityError


def test_add_message_appends_to_buffer():
    s = ManagedSession(session_id="x", project_name="demo")
    s.add_message({"type": "assistant", "text": "hi"})
    assert s.buffer[-1]["text"] == "hi"


def test_pending_question_lifecycle():
    s = ManagedSession(session_id="x", project_name="demo")
    q = s.add_pending_question({"id": "q1", "questions": []})
    assert isinstance(q, PendingQuestion)
    assert s.resolve_pending_question("q1", {"a": "b"}) is True


def test_capacity_error_is_exception():
    assert issubclass(SessionCapacityError, Exception)
```

（注：`ManagedSession` 的實際必填欄位以 `session_manager.py:78` dataclass 定義為準；測試的建構參數須對齊原 dataclass 欄位。執行時若欄位不符，以原始碼為準調整測試。）

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run python -m pytest tests/test_managed_session.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 搬移 `ManagedSession` 群**

把 `SessionCapacityError`(57)、`PendingQuestion`(68)、`ManagedSession`(78) 整段（含其所有 method：`add_message`、`_evict_oldest_buffer_entry`、`_broadcast_to_subscribers`、`_drain_and_signal_reconnect`、`_try_enqueue`、`_evict_non_critical`、`clear_buffer`、`add_pending_question`、`resolve_pending_question`、`cancel_pending_questions`、`get_pending_question_payloads`）原樣搬入 `managed_session.py`。連同 `_utc_now_iso` 若僅此處用到則一併帶走（否則保留共用）。

- [ ] **Step 4: 跑測試確認通過**

Run: `uv run python -m pytest tests/test_managed_session.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: `session_manager.py` 改 import**

刪除原定義，改 `from server.agent_runtime.managed_session import ManagedSession, PendingQuestion, SessionCapacityError`。檢查 `models.py` 等是否也 import 過這些符號，一併指向新模組。

- [ ] **Step 6: 跑全套測試確認等價**

Run: `uv run python -m pytest tests/ -q`
Expected: `1673 passed`（注意 `tests/test_session_manager_more.py` 已被你改過，確認其 import 路徑）

- [ ] **Step 7: lint + commit**

```bash
uv run ruff check --fix server/agent_runtime/managed_session.py server/agent_runtime/session_manager.py tests/test_managed_session.py
uv run ruff format server/agent_runtime/managed_session.py server/agent_runtime/session_manager.py tests/test_managed_session.py
git add server/agent_runtime/managed_session.py server/agent_runtime/session_manager.py tests/test_managed_session.py
git commit -m "refactor(agent_runtime): 抽出 ManagedSession 為獨立模組"
```

---

### Task 6: 抽出 `sdk_process_control.py`（process 生命週期）

**Files:**
- Create: `server/agent_runtime/sdk_process_control.py`
- Modify: `server/agent_runtime/session_manager.py`
- Create: `tests/test_sdk_process_control.py`

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_sdk_process_control.py
from server.agent_runtime.sdk_process_control import process_pid, process_returncode


class _FakeProc:
    pid = 4321
    returncode = 0


def test_process_pid_reads_attr():
    assert process_pid(_FakeProc()) == 4321


def test_process_returncode_reads_attr():
    assert process_returncode(_FakeProc()) == 0


def test_process_pid_handles_none():
    assert process_pid(None) is None
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run python -m pytest tests/test_sdk_process_control.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 搬移為模組函式**

把 `_get_client_process`、`_process_pid`、`_process_returncode`(三者 static)、`_wait_for_process_exit`、`_force_close_client_process`、`_cancel_task` 搬成模組級 `async`/同步函式（去掉 `self`，`_wait_for_process_exit`/`_force_close_client_process` 內部對 `self._process_returncode`/`self._wait_for_process_exit` 的呼叫改為模組內函式呼叫）。

```python
# server/agent_runtime/sdk_process_control.py
import asyncio
from typing import Any


def get_client_process(client: Any) -> Any:
    ...  # 從 session_manager.py:856 搬入

def process_pid(process: Any) -> int | None:
    ...  # 從 session_manager.py:864 搬入

def process_returncode(process: Any) -> int | None:
    ...  # 從 session_manager.py:869 搬入

async def cancel_task(task: asyncio.Task | None) -> None:
    ...  # 從 session_manager.py:873 搬入

async def wait_for_process_exit(process: Any, timeout: float) -> bool:
    ...  # 從 session_manager.py:880 搬入；self._process_returncode → process_returncode

async def force_close_client_process(client: Any, ...) -> None:
    ...  # 從 session_manager.py:900 搬入；內部呼叫改模組函式
```

- [ ] **Step 4: 跑測試確認通過**

Run: `uv run python -m pytest tests/test_sdk_process_control.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: `session_manager.py` 改委派**

刪原 method，呼叫點改 `sdk_process_control.wait_for_process_exit(...)` 等。`import server.agent_runtime.sdk_process_control as proc` 後全檔替換呼叫點（`self._wait_for_process_exit` → `proc.wait_for_process_exit`）。

- [ ] **Step 6: 跑全套測試確認等價**

Run: `uv run python -m pytest tests/ -q`
Expected: `1673 passed`（重點看 `_disconnect_session`/`close_session`/shutdown 相關測試）

- [ ] **Step 7: lint + commit**

```bash
uv run ruff check --fix server/agent_runtime/sdk_process_control.py server/agent_runtime/session_manager.py tests/test_sdk_process_control.py
uv run ruff format server/agent_runtime/sdk_process_control.py server/agent_runtime/session_manager.py tests/test_sdk_process_control.py
git add server/agent_runtime/sdk_process_control.py server/agent_runtime/session_manager.py tests/test_sdk_process_control.py
git commit -m "refactor(agent_runtime): 抽出 sdk_process_control process 控制"
```

---

### Task 7: 抽出 `session_prompt_builder.py`（純函式 prompt 拼接）

**Files:**
- Create: `server/agent_runtime/session_prompt_builder.py`
- Modify: `server/agent_runtime/session_manager.py`
- Create: `tests/test_session_prompt_builder.py`

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_session_prompt_builder.py
from server.agent_runtime.session_prompt_builder import append_overview_section, build_project_context


def test_append_overview_section_noop_on_none():
    parts: list[str] = []
    append_overview_section(parts, None)
    assert parts == []


def test_build_project_context_includes_name():
    ctx = build_project_context(project_name="demo", project={"title": "T"}, overview=None)
    assert "demo" in ctx
```

（注：`build_project_context` 原為 `self._build_project_context(project_name)`，內部會自行 load project/overview；重構為純函式須把它依賴的資料改為參數傳入。執行時對齊 `session_manager.py:351` 的實際讀取來源，將 load 行為留在呼叫端，builder 只負責拼字串。）

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run python -m pytest tests/test_session_prompt_builder.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 搬移為純函式**

把 `_build_append_prompt`、`_build_project_context`、`_append_overview_section`(static) 搬成模組級純函式，所有原本由 `self` 取得的資料（project、overview、config 值）改為參數。`session_manager` 在呼叫前先把資料準備好傳入。

- [ ] **Step 4: 跑測試確認通過**

Run: `uv run python -m pytest tests/test_session_prompt_builder.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: `session_manager.py` 改呼叫**

`_build_options` 內 `self._build_append_prompt(project_name)` 改為先取資料再呼叫 `session_prompt_builder.build_append_prompt(...)`。**`_build_options` 本身保留在類內**（耦合 `data_dir`/`max_turns`/`_is_path_allowed`/`_keep_stream_open_hook`/`_resolve_project_cwd`，不抽）。

- [ ] **Step 6: 跑全套測試確認等價**

Run: `uv run python -m pytest tests/ -q`
Expected: `1673 passed`

- [ ] **Step 7: lint + commit**

```bash
uv run ruff check --fix server/agent_runtime/session_prompt_builder.py server/agent_runtime/session_manager.py tests/test_session_prompt_builder.py
uv run ruff format server/agent_runtime/session_prompt_builder.py server/agent_runtime/session_manager.py tests/test_session_prompt_builder.py
git add server/agent_runtime/session_prompt_builder.py server/agent_runtime/session_manager.py tests/test_session_prompt_builder.py
git commit -m "refactor(agent_runtime): 抽出 session_prompt_builder 純函式"
```

---

### Task 8: 把權限/工具回呼移入 `session_hooks.py`

**Files:**
- Modify: `server/agent_runtime/session_hooks.py`
- Modify: `server/agent_runtime/session_manager.py`
- Create: `tests/test_session_hooks_path.py`

> **耦合注意**：`_is_path_allowed` 依賴 `self.project_root` + `_encode_sdk_project_path`，須把 `_encode_sdk_project_path` 一起帶走。`_build_can_use_tool_callback` 依賴 `self._handle_ask_user_question` + `self.sessions`，抽成 hook 工廠時以參數注入 `handle_ask_user_question` callable 與 `sessions` 引用。

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_session_hooks_path.py
from pathlib import Path

from server.agent_runtime.session_hooks import encode_sdk_project_path, is_path_allowed


def test_encode_sdk_project_path_is_deterministic(tmp_path: Path):
    a = encode_sdk_project_path(tmp_path / "demo")
    b = encode_sdk_project_path(tmp_path / "demo")
    assert a == b


def test_is_path_allowed_rejects_outside_root(tmp_path: Path):
    root = tmp_path / "projects"
    root.mkdir()
    assert is_path_allowed(str(root / "demo" / "a.txt"), project_root=root) is True
    assert is_path_allowed("/etc/passwd", project_root=root) is False
```

（注：`is_path_allowed` 的實際允許規則以 `session_manager.py:1235` 為準，含對 SDK encoded path 的處理；測試斷言須對齊原邏輯，必要時調整。）

- [ ] **Step 2: 跑測試確認失敗**

Run: `uv run python -m pytest tests/test_session_hooks_path.py -v`
Expected: FAIL（`ImportError: cannot import name`）

- [ ] **Step 3: 搬移**

把 `_encode_sdk_project_path`(static)、`_is_path_allowed`、`_handle_ask_user_question`、`_build_can_use_tool_callback` 搬入 `session_hooks.py`：
- `encode_sdk_project_path(project_cwd)` 模組函式。
- `is_path_allowed(path, *, project_root)` 模組函式（`_encode_sdk_project_path` 改呼叫模組內 `encode_sdk_project_path`）。
- `build_can_use_tool_callback(*, sessions, handle_ask_user_question, project_root)` 工廠函式，回傳 callback。
- `handle_ask_user_question` 改成接受 `managed`/`payload` 參數的模組函式（或留在類內僅暴露給工廠注入——以最小改動為準）。

- [ ] **Step 4: 跑測試確認通過**

Run: `uv run python -m pytest tests/test_session_hooks_path.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: `session_manager.py` 改委派**

`_is_path_allowed`/`_encode_sdk_project_path` 呼叫點改 `session_hooks.is_path_allowed(path, project_root=self.project_root)`。`_build_can_use_tool_callback` 改為 `session_hooks.build_can_use_tool_callback(sessions=self.sessions, handle_ask_user_question=self._handle_ask_user_question, project_root=self.project_root)`。

- [ ] **Step 6: 跑全套測試確認等價**

Run: `uv run python -m pytest tests/ -q`
Expected: `1673 passed`（重點看權限 gate / can_use_tool / ask_user_question 相關測試）

- [ ] **Step 7: lint + commit**

```bash
uv run ruff check --fix server/agent_runtime/session_hooks.py server/agent_runtime/session_manager.py tests/test_session_hooks_path.py
uv run ruff format server/agent_runtime/session_hooks.py server/agent_runtime/session_manager.py tests/test_session_hooks_path.py
git add server/agent_runtime/session_hooks.py server/agent_runtime/session_manager.py tests/test_session_hooks_path.py
git commit -m "refactor(agent_runtime): 權限/工具回呼移入 session_hooks"
```

---

## 收尾驗收（所有 Task 完成後）

- [ ] **行數複查**

Run:
```bash
for f in lib/project_manager.py lib/project_paths.py lib/project_store.py lib/script_repository.py lib/symlink_repair.py lib/overview_generator.py server/agent_runtime/session_manager.py server/agent_runtime/managed_session.py server/agent_runtime/sdk_process_control.py server/agent_runtime/session_prompt_builder.py server/agent_runtime/session_hooks.py; do printf "%6d  %s\n" "$(wc -l < "$f")" "$f"; done
```
Expected: `project_manager.py` ≤ ~500、`session_manager.py` ≤ ~900。

- [ ] **全套測試 + lint + format check**

Run:
```bash
uv run python -m pytest tests/ -q
uv run ruff check .
uv run ruff format --check .
```
Expected: `1673 passed`、`All checks passed!`、format 無 diff。

- [ ] **整庫 import smoke test**

Run:
```bash
uv run python -c "import server.app" 2>&1 | tail -3 || uv run python -c "import server.main" 2>&1 | tail -3
```
Expected: 無 ImportError。

---

## Self-Review 紀錄

- **Spec coverage**：ProjectManager 5 個子模組 + SessionManager 4 個子模組，覆蓋使用者「彻底按职责完整分层」要求。`get_project_status`/`sync_project_status`（跨域聚合）刻意保留在 PM，因其協調多個 collaborator。
- **Placeholder scan**：所有「原樣搬入」步驟標註了確切來源行號；測試含完整可執行碼。`...` 僅用於標示「從指定行號搬入既有實作」，非待填。
- **Type consistency**：collaborator 注入命名一致（`self._paths`/`self._store`/`self._scripts`）；`ProjectPaths`/`ProjectStore`/`ScriptRepository` 建構參數在各 Task 間一致。
- **已知風險**：(1) `_build_options` 不抽，故 session_manager 可能停在 ~800–900 行而非 <800，這是刻意取捨（避免破壞深耦合）。(2) Task 7/8 把「load 資料」責任上移到呼叫端，須確保不改變 load 時機（避免少 load 或重複 load）。(3) `tests/test_session_manager_more.py` 已有未提交改動，Task 5 前須先確認其當前內容與 import。
