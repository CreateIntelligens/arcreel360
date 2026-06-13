#!/usr/bin/env python3
"""
normalize_drama_script.py - 使用 Gemini Pro 生成規範化劇本

將 source/ 小說原文轉化為 Markdown 格式的規範化劇本（step1_normalized_script.md），
供 generate_script.py 消費。

用法:
    python normalize_drama_script.py --episode <N>
    python normalize_drama_script.py --episode <N> --source <file>
    python normalize_drama_script.py --episode <N> --dry-run
"""

import argparse
import json
import re
import sys
from pathlib import Path

# 允許從倉庫任意工作目錄直接執行該指令碼
PROJECT_ROOT = (
    Path(__file__).resolve().parents[5]
)  # agent_runtime_profile/.claude/skills/generate-script/scripts -> repo root
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import asyncio

from lib.project_manager import ProjectManager
from lib.text_backends.base import TextGenerationRequest, TextTaskType
from lib.text_backends.factory import create_text_backend_by_model_str, create_text_backend_for_task


def build_normalize_prompt(
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
    """構建規範化劇本的 Prompt。

    Args:
        characters / clues / scenes:「已篩選後」的 dict——呼叫端負責挑選要帶哪些 key。
            傳空 dict `{}` 代表「不帶該區塊」（整段 `<...>` 標籤省略）；
            scenes=None 跟 `{}` 等價（都不帶，維持向後相容）。
        include_overview / include_style：False 代表完全省略該區塊。
        num_segments: 指定生成的場景數量。
    """

    def _name_only(items: dict) -> str:
        return "\n".join(f"- {name}" for name in items.keys()) or "（暫無）"

    def _name_with_desc(items: dict) -> str:
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
            f"題材型別：{project_overview.get('genre', '')}\n"
            f"核心主題：{project_overview.get('theme', '')}\n"
            f"世界觀設定：{project_overview.get('world_setting', '')}\n"
            "</overview>"
        )
    if include_style:
        sections.append(f"<style>\n{style}\n</style>")
    # characters / clues / scenes：空 dict → 完全省略該 <...> 區塊。
    if characters:
        sections.append(f"<characters>\n{_name_with_desc(characters)}\n</characters>")
    if clues:
        sections.append(f"<clues>\n{_name_with_desc(clues)}\n</clues>")
    if scenes:
        sections.append(f"<scenes>\n{_name_with_desc(scenes)}\n</scenes>")

    info_block = ("## 專案資訊\n\n" + "\n\n".join(sections) + "\n\n") if sections else ""

    if num_segments is not None:
        rule_num_segments = f"\n- **指定場景數量**：必須將小說原文合理且均勻地改編並拆分為**剛好 {num_segments}** 個場景（輸出 {num_segments} 列 Markdown 表格，場景 ID 從 E{{集數}}S01 到 E{{集數}}S{num_segments:02d}）。"
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

    return f"""你的任務是將小說原文改編為結構化的分鏡場景表（Markdown 格式），用於後續 AI 影片生成。

## 核心原則

1. **忠於原作**：保留小說的核心情節、角色對話與氛圍，僅在必要時進行精簡或改編為旁白。
2. **場景切換**：以時間跳躍、空間轉換、視角切換或重大情節轉折為基準拆分場景。{rule_num_segments}
3. **角色與線索關聯**：準確提取每個場景中「出場的角色」與「出現的道具/線索」，使用 bare name，多個以逗號分隔，若無則填「-」。

## 輸出欄位說明

固定輸出以下 **9 欄**，欄位順序與名稱必須完全一致，不得增減或改名：

- **場景 ID**：格式為 `E{{episode:02d}}S{{scene_idx:02d}}`（例如第一集第一個場景為 `E01S01`）
- **場景描述**：詳細刻畫該場景的畫面內容，用自然語言描述，為後續生圖/生影片 Prompt 奠定基礎
- **旁白**：該場景的旁白／獨白配音文字（對鏡頭說話、第三人稱敘述、內心獨白皆屬此類），用於後期配音；若無旁白填「-」
- **對話**：該場景中角色之間的直接對白，格式為 `角色名：台詞`，多句以換行分隔（在同一格內換行）；角色名須為 `characters` 清單裡的裸名；若無對白填「-」
- **出場的角色**：該場景內說話、被提及或出鏡的角色名字（必須是 `characters` 清單中已定義的裸名，如「林克」而非「@林克」），多個以逗號分隔，無則填「-」
- **出現的道具**：該場景中關鍵物品/線索名字（必須是 `clues` 清單中已定義的裸名），多個以逗號分隔，無則填「-」
- **場景**：指明本場景的地點名字（必須是 `scenes` 清單中已定義的裸名），無則填「-」
- **時長**：該場景預估播放時間（秒），必須為整數且在 4 到 15 秒之間（預設為 8 秒）
- **segment_break**：場景切換點（時間跳躍／空間轉換／視角切換／重大情節轉折）填「是」，同一連續場景填「否」

### 旁白與對話的分流（重要）
- **旁白**與**對話**是兩個獨立欄位，不可混填：旁白是「畫外音／敘述／獨白」，對話是「角色之間你來我往的台詞」。
- 例：角色對著鏡頭自我介紹、第三人稱敘事 → 填入**旁白**欄，**對話**欄填「-」。
- 例：兩個角色互相交談 → 逐句填入**對話**欄（`角色名：台詞`），若同時也有旁白才填旁白欄。
- 一個場景可以只有旁白、只有對話、兩者皆有、或兩者皆無（皆填「-」）。

{info_block}## 小說原文

<novel>
{novel_text}
</novel>

## 輸出要求

將小說改編為場景列表，使用 Markdown 表格格式，**欄位必須與上方「輸出欄位說明」完全一致的 9 欄**：

| 場景 ID | 場景描述 | 旁白 | 對話 | 出場的角色 | 出現的道具 | 場景 | 時長 | segment_break |
|---------|---------|------|------|-----------|-----------|------|------|---------------|
| E{{N}}S01 | 詳細的場景描述... | 大家好，我是… | - | 沈文程 | 釣竿 | 岩岸 | 8 | 是 |
| E{{N}}S02 | 詳細的場景描述... | - | 小明：你看那邊！<br>小華：真的耶！ | 小明, 小華 | - | 防波堤 | 8 | 否 |

規則：
- 場景 ID 格式：E{{集數}}S{{兩位序號}}（如 E1S01, E1S02）{rule_num_segments}
- 場景描述：改編後的劇本化描述，包含角色動作、環境，適合視覺化呈現（純畫面描述，台詞放「對話」欄、旁白放「旁白」欄）
- 旁白：畫外音／獨白／敘述，無則填「-」
- 對話：角色直接對白，格式 `角色名：台詞`，多句用 `<br>` 或換行分隔；無則填「-」
- 時長：4、6 或 8 秒（預設 8 秒，簡單畫面可用 4 或 6 秒）
- segment_break：場景切換點標記"是"，同一連續場景標"否"
- 每個場景應為一個獨立的視覺畫面，可以在指定時長內完成
- 避免一個場景包含多個不同的動作或畫面切換
- **標準名稱套用與改寫（關鍵）**：
  在改寫小說原文編寫「場景描述」時，**必須主動對照並套用**角色、線索與場景清單中所列的標準名稱。
  - 如果小說原文中使用了人物的代稱或別名（例如「老人」、「老法師」），必須主動映射並直接改寫替換為專案定義的標準角色名稱。
  - 如果小說原文中提到道具或線索的略稱，必須主動替換為對應的標準線索名稱。
  - 若該場景發生的空間地點對應了專案已設定的標準場景，必須在描述中明確寫出該標準場景名稱，並儘量融入其在場景清單中的描述特徵，以保持影片前後場景環境的一致性。

### 嚴禁標記符號
「場景描述」欄位是給後續 AI 讀的自然語言，**不得**自行添加 `@xxx`、`#xxx`、`[xxx]`、`{{xxx}}` 等任何引用標記。
- 系統下游使用結構化欄位（characters_in_scene / clues_in_scene / scene）及白名單裸名比對來建立實體關聯，標記符號不會被解析。
- 即使描述裡的某個名詞（例如「書房」「客廳」）讓你聯想到場景，也**不可**加 @ 標。未列於角色、線索或場景清單的名稱一律不得標記。
- 若清單為空或未提供，描述一律保持純文字，不得自創任何標記語法。
- 直接寫角色名、道具名、場景名即可（例如「天安門」而非「@天安門」），下游會自動比對白名單。

僅輸出 Markdown 表格，不要包含其他解釋文字。
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

    project.json 不存在 / 無 episodes / 該集不在列表 → 退化為 (1, 1),
    亦即把整本當單一一集,確保仍可規範化。
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
    1. 使用者指定 source → 讀該檔。
    2. source/episode_{episode}.txt 存在 → 讀它（進階使用者手動精切的產物）。
    3. 否則 → 讀 source/ 整本原文,按 project.json 的集數均分,取本集那一段
       (與 narration 模式對齊;早期版本是「直接回傳整本」造成多集生成相同內容)。

    Raises:
        ValueError: 指定的 source 路徑超出 source/ 目錄。
        FileNotFoundError: 指定的 source 檔不存在或路徑無效。
        SourceNotReadyError: 未指定 source 且 source/ 內無原文檔／整本內容為空／
            均分後該集為空。
    """
    if source is not None:
        return _read_explicit_sources(project_path, source)

    candidate = project_path / "source" / f"episode_{episode}.txt"
    if candidate.exists():
        return _read_source_file(candidate)

    whole = _read_whole_source(project_path / "source")
    if not whole.strip():
        raise SourceNotReadyError("source/ 內沒有可用的小說原文。請先在資產面板上傳小說原文檔，再執行規範化。")

    from lib.episode_splitter import split_into_n_episodes

    index, total = _episode_index_and_total(project_path, episode)
    parts = split_into_n_episodes(whole, total)
    result = parts[index - 1]
    if not result.strip():
        raise SourceNotReadyError(
            f"均分原文後第 {episode} 集的內容為空。整本原文共計 {len(whole)} 字,無法均分成 {total} 集。請確認小說字數是否足夠或集數設定是否正確。"
        )
    return result


def main():
    parser = argparse.ArgumentParser(
        description="使用 Gemini Pro 生成規範化劇本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
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
        help="指定生成的場景數量",
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
        help="使用者於 WebUI 輸入的自由提示詞，用於引導改編",
    )

    args = parser.parse_args()

    # 構建專案路徑
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

    # 構建 Prompt
    prompt = build_normalize_prompt(
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
        print("DRY RUN - 以下是將傳送給 Gemini 的 Prompt:")
        print("=" * 60)
        print(prompt)
        print("=" * 60)
        print(f"\nPrompt 長度: {len(prompt)} 字元")
        return

    # 呼叫 TextBackend
    async def _run():
        backend = (
            await create_text_backend_by_model_str(args.model)
            if args.model
            else await create_text_backend_for_task(TextTaskType.SCRIPT, project_name)
        )
        print(f"正在使用 {backend.model} 生成規範化劇本...")
        result = await backend.generate(TextGenerationRequest(prompt=prompt))
        return result.text

    response = asyncio.run(_run())

    # 儲存檔案
    drafts_dir = project_path / "drafts" / f"episode_{args.episode}"
    drafts_dir.mkdir(parents=True, exist_ok=True)

    step1_path = drafts_dir / "step1_normalized_script.md"
    step1_path.write_text(response.strip(), encoding="utf-8")
    print(f"✅ 規範化劇本已儲存: {step1_path}")

    # 簡要統計
    lines = [
        line
        for line in response.split("\n")
        if line.strip().startswith("|") and "場景 ID" not in line and "---" not in line
    ]
    scene_count = len(lines)
    print(f"\n📊 生成統計: {scene_count} 個場景")


if __name__ == "__main__":
    main()
