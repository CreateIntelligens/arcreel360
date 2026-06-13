import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path


def read_docx_text(file_path: Path | str) -> str:
    """從 .docx 檔案中提取純文字內容。

    使用 Python 內建的 zipfile 和 xml.etree.ElementTree，無外部依賴。
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"檔案不存在: {file_path}")

    try:
        with zipfile.ZipFile(file_path) as docx:
            xml_content = docx.read("word/document.xml")
            root = ET.fromstring(xml_content)

            paragraphs = []
            p_tag = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"
            t_tag = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"

            for p in root.iter(p_tag):
                texts = []
                for t in p.iter(t_tag):
                    if t.text:
                        texts.append(t.text)
                paragraphs.append("".join(texts))

            return "\n".join(paragraphs)
    except Exception as e:
        raise ValueError(f"解析 .docx 檔案失敗: {e}")
