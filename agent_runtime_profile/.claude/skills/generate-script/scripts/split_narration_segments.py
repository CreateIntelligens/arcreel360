#!/usr/bin/env python3
"""
split_narration_segments.py - 使用 LLM 將小說原文拆分為說書模式片段

用法:
    python split_narration_segments.py --episode <N>
    python split_narration_segments.py --episode <N> --source <file>
    python split_narration_segments.py --episode <N> --dry-run
"""

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = (
    Path(__file__).resolve().parents[5]
)  # agent_runtime_profile/.claude/skills/generate-script/scripts -> repo root
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import asyncio

from lib.project_manager import ProjectManager
from lib.text_backends.base import TextGenerationRequest, TextTaskType
from lib.text_backends.factory import create_text_backend_by_model_str, create_text_backend_for_task


def build_split_prompt(
    novel_text: str,
    project_overview: dict,
    style: str,
    characters: dict,
    clues: dict,
    *,
    include_overview: bool = True,
    include_style: bool = True,
    scenes: dict | None = None,
    num_segments: int | None = None,
    extra_instruction: str | None = None,
) -> str:
    """構建說書片段拆分的 Prompt。

    Args:
        characters / clues / scenes:「已篩選後」的 dict——呼叫端負責挑選要帶哪些 key。
            傳空 dict `{}` 代表「不帶該區塊」(整段 `<...>` 標籤省略);
            scenes=None 跟 `{}` 等價(都不帶,維持向後相容)。
        include_overview / include_style:False 代表完全省略該區塊。
        num_segments: 指定生成的片段數量。
    """

    def _format(items: dict) -> str:
        lines = []
        for name, data in items.items():
            desc = ""
            if isinstance(data, dict):
                desc = (data.get("description") or "").strip()
            if desc:
                lines.append(f"- **{name}**：{desc}")
            else:
                lines.append(f"- **{name}**")
        return "\n".join(lines) or "（暫無）"

    project_overview = project_overview or {}
    sections: list[str] = []
    if include_overview:
        sections.append(
            "<overview>\n"
            f"{project_overview.get('synopsis', '')}\n\n"
            f"題材類型：{project_overview.get('genre', '')}\n"
            f"核心主題：{project_overview.get('theme', '')}\n"
            f"世界觀設定：{project_overview.get('world_setting', '')}\n"
            "</overview>"
        )
    if include_style:
        sections.append(f"<style>\n{style}\n</style>")
    # characters / clues / scenes：空 dict → 完全省略該 <...> 區塊（空陣列 ≠ 省略的語意由呼叫端決定）。
    if characters:
        sections.append(f"<characters>\n{_format(characters)}\n</characters>")
    if clues:
        sections.append(f"<clues>\n{_format(clues)}\n</clues>")
    if scenes:
        sections.append(f"<scenes>\n{_format(scenes)}\n</scenes>")

    info_block = ("## 專案資訊\n\n" + "\n\n".join(sections) + "\n\n") if sections else ""

    if num_segments is not None:
        rule_num_segments = f"\n4. **指定片段數量**：必須將輸入的小說原文合理且均勻地拆分為**剛好 {num_segments}** 個片段（輸出 {num_segments} 列 Markdown 表格，序號從 G01 到 G{num_segments:02d}）。確保不丟失、不重複原文內容。"
    else:
        rule_num_segments = ""

    instruction_block = ""
    if extra_instruction and extra_instruction.strip():
        instruction_block = (
            "\n## 額外調整指示 (User Instruction)\n"
            "請在符合上述硬性格式要求的前提下，特別遵照以下指示進行生成與微調：\n"
            "<user_instruction>\n"
            f"{extra_instruction.strip()}\n"
            "</user_instruction>\n"
        )

    return f"""你的任務是將中文小說原文按朗讀節奏拆分為適合短影片配音的片段，輸出 Markdown 表格。

## 核心原則

1. **保留原文**：不改編、不刪減、不新增小說原文內容；每個片段的「原文」欄位必須是小說中的連續一段文字。
2. **朗讀節奏**：每片段約 4 秒（約 20-24 個中文字），在自然斷句處拆分。
3. **片段拼接後等於原文**：把所有片段「原文」依序串起，應與輸入小說（去除前後空白）等價。{rule_num_segments}

## 拆分規則

### 時長
- 預設 4 秒（約 20-24 個中文字）
- 長句（超過 24 字）可用 6 秒或 8 秒
- 保持語義完整性，不拆斷完整的語義單元

### 拆分點
- 優先在句號、問號、感嘆號、省略號等標點處拆分
- 段落結束處拆分
- 對話前後可拆分，但對話本體不要在中途拆斷

### 對話標記
- 識別包含角色對話的片段：含 `「」`、`""` 或「XXX說道」等敘述性引語
- 在「有對話」欄位標記「是」，否則標「否」

### 場景切換（segment_break）
- 在真正的場景切換點標記「是」：時間跳躍、空間轉換、視角切換、重大情節轉折
- 同一連續場景內標記「-」
- 不要濫用；多數片段應為「-」

{info_block}## 小說原文

<novel>
{novel_text}
</novel>

## 輸出格式

僅輸出以下 Markdown，不要包含任何其他解釋文字：

```markdown
## 片段拆分結果

| 片段 | 原文 | 字數 | 時長 | 有對話 | segment_break |
|------|------|------|------|--------|---------------|
| G01 | …原文… | 22 | 4s | 否 | - |
| G02 | …原文… | 24 | 4s | 是 | - |
| G03 | …原文… | 6  | 4s | 否 | 是 |
```

規則：
- 片段編號從 G01 開始遞增（兩位數補零）
- 「原文」欄位若包含 `|` 字符，請以 `\\|` 跳脫
- 「字數」為原文中文字數（可粗略估計）
- 「時長」只能是 `4s`、`6s` 或 `8s`
- 「有對話」只能是 `是` 或 `否`
- 「segment_break」只能是 `是` 或 `-`

### 嚴禁標記符號
原文必須是小說中的連續一段純文字，**不得**自行添加 `@xxx`、`#xxx`、`[xxx]`、`{{xxx}}` 等任何引用標記。
- 系統下游使用結構化欄位（characters_in_segment / clues_in_segment / scene）及白名單裸名比對來建立實體關聯，標記符號不會被解析。
- 即使原文裡的某個名詞（例如「書房」「客廳」）讓你聯想到場景，也**不可**加 @ 標。未列於角色、線索或場景清單的名稱一律不得標記。
- 若清單為空或未提供，原文一律保持純文字，不得自創任何標記語法。
{instruction_block}"""


def _filter_by_names(items: dict, names_csv: str | None) -> dict:
    """依 CLI 旗標值篩選 dict。

    - ``names_csv is None`` → 不篩選，原樣回傳（「全帶」語意）。
    - ``names_csv == ""`` → 回傳空 dict（「都不帶」語意）。
    - 否則：以 ASCII Unit Separator (U+001F) 分隔取 token，只保留 items 內存在的 key
      （不存在的名字靜默忽略）。**不做 strip**:project.json 的 dict key 可能含前後空白,
      strip 會讓 `name in items` 對不上。
    """
    if names_csv is None:
        return items
    if not names_csv:
        return {}
    names = names_csv.split(_REF_NAME_SEPARATOR)
    return {name: items[name] for name in names if name in items}


# 「尚未分集切分」專用退出碼：run_preprocess 依此把錯誤映射成 HTTP 400。
SOURCE_NOT_READY_EXIT_CODE = 3

# 視為小說原文的副檔名（單檔 fallback 用）。
_SOURCE_SUFFIXES = (".txt", ".md", ".text", ".docx")
_REF_NAME_SEPARATOR = "\x1f"


class SourceNotReadyError(FileNotFoundError):
    """缺少可用的小說原文，需使用者上傳或指定來源。

    繼承 FileNotFoundError 以沿用 resolve_novel_text 呼叫端既有的 except 分支；
    main() 會把它對應到 SOURCE_NOT_READY_EXIT_CODE 退出。
    """


def _read_source_file(path: Path) -> str:
    from lib.docx_utils import read_docx_text
    from lib.source_text import read_text_with_fallback

    if path.suffix.lower() == ".docx":
        return read_docx_text(path)
    return read_text_with_fallback(path)


def _episode_source_files(source_dir: Path) -> list[Path]:
    """列出 source/ 內可視為小說原文的檔案（排除分集切分產生的 _remaining.txt 與 episode_N.txt）。"""
    if not source_dir.is_dir():
        return []
    return sorted(
        f
        for f in source_dir.iterdir()
        if (
            f.is_file()
            and f.suffix.lower() in _SOURCE_SUFFIXES
            and f.name != "_remaining.txt"
            and not re.match(r"^episode_\d+\.(txt|md|text)$", f.name, re.IGNORECASE)
        )
    )


def _read_whole_source(source_dir: Path) -> str:
    """把 source/ 內所有原文檔按檔名排序串接成「整本原文」。"""
    files = _episode_source_files(source_dir)

    texts = []
    for f in files:
        texts.append(_read_source_file(f))
    return "\n\n".join(texts)


def _read_explicit_sources(project_path: Path, source: str) -> str:
    """讀取使用者明確指定的 source/ 內一或多個原文檔。"""
    if not source.strip():
        raise FileNotFoundError("未指定原始檔路徑(指定了空路徑)")

    source_root = (project_path / "source").resolve()
    sources = [s.strip() for s in source.split(",") if s.strip()]
    if not sources:
        raise FileNotFoundError("未指定原始檔路徑(指定了空路徑)")

    texts = []
    for src in sources:
        source_path = (project_path / src).resolve()
        if not source_path.is_relative_to(source_root):
            raise ValueError(f"路徑超出 source/ 目錄: {source_path}")
        if not source_path.exists() or source_path.is_dir():
            raise FileNotFoundError(f"未找到原始檔: {source_path}")
        if source_path.suffix.lower() not in _SOURCE_SUFFIXES:
            raise ValueError(f"不支援的原始檔格式: {source_path.suffix}，僅支援: {', '.join(_SOURCE_SUFFIXES)}")

        texts.append(_read_source_file(source_path))
    return "\n\n".join(texts)


def _episode_index_and_total(project_path: Path, episode: int) -> tuple[int, int]:
    """從 project.json 算出 (該集在升序集列表中的 1-based 索引, 總集數)。

    project.json 不存在 / 無 episodes / 該集不在列表 → 退化為 (1, 1)，
    亦即把整本當單一一集，確保仍可拆段。
    """
    project_json = project_path / "project.json"
    if not project_json.exists():
        return (1, 1)
    try:
        data = json.loads(project_json.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return (1, 1)
    episodes = data.get("episodes") or []
    numbers = sorted(int(ep["episode"]) for ep in episodes if isinstance(ep, dict) and "episode" in ep)
    if not numbers or episode not in numbers:
        return (1, 1)
    return (numbers.index(episode) + 1, len(numbers))


def resolve_novel_text(project_path: Path, episode: int, source: str | None) -> str:
    """決定並讀取某集的小說原文。

    解析順序：
    1. 使用者指定 source → 讀該檔（覆寫自動均分）。
    2. source/episode_{episode}.txt 存在 → 讀它（進階使用者手動精切的產物）。
    3. 否則 → 讀 source/ 整本原文，按 project.json 的集數均分，取本集那一段。

    Raises:
        ValueError: 指定的 source 路徑超出專案目錄。
        FileNotFoundError: 指定的 source 檔不存在或路徑無效。
        SourceNotReadyError: 未指定 source 且 source/ 內無原文檔／整本內容為空／均分後該集為空。
    """
    if source is not None:
        return _read_explicit_sources(project_path, source)

    candidate = project_path / "source" / f"episode_{episode}.txt"
    if candidate.exists():
        return _read_source_file(candidate)

    whole = _read_whole_source(project_path / "source")
    if not whole.strip():
        raise SourceNotReadyError("source/ 內沒有可用的小說原文。請先在資產面板上傳小說原文檔，再執行拆段。")

    from lib.episode_splitter import split_into_n_episodes

    index, total = _episode_index_and_total(project_path, episode)
    parts = split_into_n_episodes(whole, total)
    result = parts[index - 1]
    if not result.strip():
        raise SourceNotReadyError(
            f"均分原文後第 {episode} 集的內容為空。整本原文共計 {len(whole)} 字，無法均分成 {total} 集。請確認小說字數是否足夠或集數設定是否正確。"
        )
    return result


def main():
    parser = argparse.ArgumentParser(
        description="""使用 LLM 將小說原文拆分為說書模式片段。
預設會輸出 Markdown 片段表到 drafts/episode_{episode}/step1_segments.md。

使用範例:
    %(prog)s --episode 1
    %(prog)s --episode 1 --source source/episode_1.txt
    %(prog)s --episode 1 --dry-run
        """,
    )

    parser.add_argument("--episode", "-e", type=int, required=True, help="劇集編號")
    parser.add_argument(
        "--source",
        "-s",
        type=str,
        default=None,
        help="指定小說原始檔路徑，可用逗號分隔多檔（預設讀 source/episode_{N}.txt）",
    )
    parser.add_argument(
        "--num-segments",
        type=int,
        default=None,
        help="指定生成的片段數量",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="指定文字模型，格式為 provider/model；不指定則使用專案或全域劇本模型",
    )
    parser.add_argument("--dry-run", action="store_true", help="僅顯示 Prompt，不實際呼叫 API")
    parser.add_argument(
        "--no-overview",
        action="store_true",
        help="不在 prompt 內帶入 <overview> 區塊（預設帶）",
    )
    parser.add_argument(
        "--no-style",
        action="store_true",
        help="不在 prompt 內帶入 <style> 區塊（預設帶）",
    )
    parser.add_argument(
        "--characters-only",
        type=str,
        default=None,
        help="逗號分隔字串，只把這些角色名帶入 prompt；空字串代表完全不帶；不指定代表全帶",
    )
    parser.add_argument(
        "--clues-only",
        type=str,
        default=None,
        help="逗號分隔字串，只把這些線索名帶入 prompt；空字串代表完全不帶；不指定代表全帶",
    )
    parser.add_argument(
        "--scenes-only",
        type=str,
        default=None,
        help="逗號分隔字串，只把這些場景名帶入 prompt；空字串代表完全不帶；不指定代表全帶",
    )
    parser.add_argument(
        "--instruction",
        type=str,
        default=None,
        help="使用者於 WebUI 輸入的自由提示詞，用於引導拆分",
    )

    args = parser.parse_args()

    pm, project_name = ProjectManager.from_cwd()
    project_path = pm.get_project_path(project_name)
    project = pm.load_project(project_name)

    # 讀取小說原文
    try:
        novel_text = resolve_novel_text(project_path, args.episode, args.source)
    except SourceNotReadyError as e:
        # 尚未分集切分：可由使用者修正，用專用退出碼讓上層映射成 HTTP 400。
        sys.stderr.write(f"SourceNotReadyError: {e}\n")
        print(f"❌ {e}")
        sys.exit(SOURCE_NOT_READY_EXIT_CODE)
    except (ValueError, FileNotFoundError) as e:
        print(f"❌ {e}")
        sys.exit(1)

    if not novel_text.strip():
        print("❌ 小說原文為空")
        sys.exit(1)

    characters = _filter_by_names(project.get("characters", {}) or {}, args.characters_only)
    clues = _filter_by_names(project.get("clues", {}) or {}, args.clues_only)
    scenes = _filter_by_names(project.get("scenes", {}) or {}, args.scenes_only)

    prompt = build_split_prompt(
        novel_text=novel_text,
        project_overview=project.get("overview") or {},
        style=project.get("style", ""),
        characters=characters,
        clues=clues,
        include_overview=not args.no_overview,
        include_style=not args.no_style,
        scenes=scenes,
        num_segments=args.num_segments,
        extra_instruction=args.instruction,
    )

    if args.dry_run:
        print("=" * 60)
        print("DRY RUN - 以下是將傳送給 LLM 的 Prompt:")
        print("=" * 60)
        print(prompt)
        print("=" * 60)
        print(f"\nPrompt 長度: {len(prompt)} 字元")
        return

    async def _run():
        backend = (
            await create_text_backend_by_model_str(args.model)
            if args.model
            else await create_text_backend_for_task(TextTaskType.SCRIPT, project_name)
        )
        print(f"正在使用 {backend.model} 拆分片段...")
        result = await backend.generate(TextGenerationRequest(prompt=prompt))
        return result.text

    response = asyncio.run(_run())

    drafts_dir = project_path / "drafts" / f"episode_{args.episode}"
    drafts_dir.mkdir(parents=True, exist_ok=True)
    step1_path = drafts_dir / "step1_segments.md"
    step1_path.write_text(response.strip(), encoding="utf-8")
    print(f"✅ 片段表已儲存: {step1_path}")

    # 簡要統計：計算 | G... | 開頭的資料行
    lines = [
        line
        for line in response.split("\n")
        if line.strip().startswith("|") and "片段" not in line and "---" not in line
    ]
    print(f"\n📊 生成統計: {len(lines)} 個片段")


if __name__ == "__main__":
    main()
