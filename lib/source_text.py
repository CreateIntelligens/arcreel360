from __future__ import annotations

from pathlib import Path

SOURCE_TEXT_ENCODINGS = ("utf-8-sig", "utf-8", "cp950", "big5")


def read_text_with_fallback(path: Path) -> str:
    """Read uploaded source text using common UTF-8 and Taiwan legacy encodings."""
    data = path.read_bytes()
    last_error: UnicodeDecodeError | None = None

    for encoding in SOURCE_TEXT_ENCODINGS:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError as exc:
            last_error = exc

    if last_error is not None:
        raise last_error
    return ""
