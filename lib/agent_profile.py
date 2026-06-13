"""Agent runtime profile 路徑常數。

集中管理 agent runtime 設定檔的目錄結構，讓所有 provider 共用同一份配置，
不再把目錄名寫死成字面值散落在程式碼裡。

目前實體目錄仍叫 `.claude/`（因為 Claude Agent SDK 透過 cwd 下的 `.claude/`
symlink 載入 settings 與 CLAUDE.md），但應用程式碼透過此模組引用，未來
改名只需修改這裡的常數 + 下列「重命名 checklist」中的靜態檔案。

重命名 checklist（若要把 `.claude` 改成別的名字）：
  1. 本模組的 `PROFILE_DIR_NAME` / `PROJECT_PROFILE_LINK_NAME` 常數
  2. 實體目錄 `agent_runtime_profile/.claude/` → 新名（git mv）
  3. 每個專案目錄裡的 symlink（`projects/*/.claude`）— 由
     `ProjectManager.repair_claude_symlink()` 自動重建，但既有專案需重跑一次
  4. `agent_runtime_profile/.claude/settings.json` 裡的 `Bash(python .claude/...)` 白名單
  5. 所有 `agent_runtime_profile/.claude/**/SKILL.md` 與 `.claude/agents/*.md` 裡的
     `python .claude/skills/...` 相對路徑、`.claude/references/...` 引用
  6. `agent_runtime_profile/CLAUDE.md` 裡的描述文字
  注意：`~/.claude/projects/` 那條（transcript 路徑）是 Claude SDK 內部寫死的，
       與本專案無關，不要動。
"""

from pathlib import Path

# agent_runtime_profile/ 底下放 profile 的子目錄名
PROFILE_DIR_NAME = ".claude"

# 每個專案目錄裡指向 profile 的 symlink 名（Claude SDK 依賴）
PROJECT_PROFILE_LINK_NAME = ".claude"

# 每個專案目錄裡指向 agent 系統 prompt 文件的 symlink 名（Claude SDK 依賴）
PROJECT_AGENT_DOC_NAME = "CLAUDE.md"

# agent_runtime_profile 外殼目錄名
RUNTIME_PROFILE_WRAPPER = "agent_runtime_profile"


def runtime_profile_root(project_root: Path) -> Path:
    """`<repo>/agent_runtime_profile/`"""
    return project_root / RUNTIME_PROFILE_WRAPPER


def profile_root(project_root: Path) -> Path:
    """`<repo>/agent_runtime_profile/<PROFILE_DIR_NAME>/`"""
    return runtime_profile_root(project_root) / PROFILE_DIR_NAME


def skills_root(project_root: Path) -> Path:
    """`<repo>/agent_runtime_profile/<PROFILE_DIR_NAME>/skills/`"""
    return profile_root(project_root) / "skills"


def agent_doc_path(project_root: Path) -> Path:
    """`<repo>/agent_runtime_profile/CLAUDE.md`"""
    return runtime_profile_root(project_root) / PROJECT_AGENT_DOC_NAME


def project_symlink_targets(project_root: Path) -> dict[str, Path]:
    """Return project symlink names mapped to their absolute profile targets."""
    return {
        PROJECT_PROFILE_LINK_NAME: profile_root(project_root),
        PROJECT_AGENT_DOC_NAME: agent_doc_path(project_root),
    }


def project_symlink_relative_targets() -> dict[str, Path]:
    """Return project symlink names mapped to targets relative to a project dir."""
    profile_base = Path("..") / ".." / RUNTIME_PROFILE_WRAPPER
    return {
        PROJECT_PROFILE_LINK_NAME: profile_base / PROFILE_DIR_NAME,
        PROJECT_AGENT_DOC_NAME: profile_base / PROJECT_AGENT_DOC_NAME,
    }


# Bash prompt 範例用的相對路徑前綴（給 LLM 看的字串）
RELATIVE_SKILLS_PREFIX = f"{PROJECT_PROFILE_LINK_NAME}/skills"
