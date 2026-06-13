import zipfile
from io import BytesIO
from pathlib import Path

import pytest

from lib.docx_utils import read_docx_text


def create_fake_docx_bytes(paragraphs: list[str]) -> bytes:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as docx:
        p_xml = ""
        for p in paragraphs:
            p_xml += f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>"

        xml_content = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f"<w:body>{p_xml}</w:body>"
            "</w:document>"
        )
        docx.writestr("word/document.xml", xml_content)
    return buf.getvalue()


def test_read_docx_text_success(tmp_path):
    docx_path = tmp_path / "test.docx"
    paragraphs = ["這是第一段文字。", "這是第二段文字。", "Hello World!"]
    docx_path.write_bytes(create_fake_docx_bytes(paragraphs))

    content = read_docx_text(docx_path)
    assert content == "這是第一段文字。\n這是第二段文字。\nHello World!"


def test_read_docx_file_not_found():
    with pytest.raises(FileNotFoundError):
        read_docx_text(Path("non_existent_file.docx"))


def test_read_docx_invalid_format(tmp_path):
    bad_path = tmp_path / "bad.docx"
    bad_path.write_text("not a zip file")
    with pytest.raises(ValueError) as excinfo:
        read_docx_text(bad_path)
    assert "解析 .docx 檔案失敗" in str(excinfo.value)
