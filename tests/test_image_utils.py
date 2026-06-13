# tests/test_image_utils.py
"""image_utils 單元測試。"""

from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from lib.image_utils import compress_image_bytes


class TestCompressImageBytes:
    """compress_image_bytes 測試。"""

    def _make_png(self, width: int, height: int) -> bytes:
        """生成指定尺寸的 PNG 位元組。"""
        img = Image.new("RGB", (width, height), color="red")
        buf = BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def test_small_image_unchanged_dimensions(self):
        """小圖（長邊 < 2048）不縮放，但仍轉為 JPEG。"""
        raw = self._make_png(800, 600)
        result = compress_image_bytes(raw)
        img = Image.open(BytesIO(result))
        assert img.format == "JPEG"
        assert img.size == (800, 600)

    def test_large_image_resized(self):
        """大圖（長邊 > 2048）縮放到長邊 2048。"""
        raw = self._make_png(4096, 3072)
        result = compress_image_bytes(raw)
        img = Image.open(BytesIO(result))
        assert img.format == "JPEG"
        assert max(img.size) == 2048
        assert img.size == (2048, 1536)

    def test_portrait_large_image(self):
        """豎圖大圖也正確縮放。"""
        raw = self._make_png(2000, 4000)
        result = compress_image_bytes(raw)
        img = Image.open(BytesIO(result))
        assert max(img.size) == 2048
        assert img.size == (1024, 2048)

    def test_rgba_converted_to_rgb(self):
        """RGBA 圖片轉為 RGB（JPEG 不支援 alpha）。"""
        img = Image.new("RGBA", (100, 100), color=(255, 0, 0, 128))
        buf = BytesIO()
        img.save(buf, format="PNG")
        result = compress_image_bytes(buf.getvalue())
        out = Image.open(BytesIO(result))
        assert out.mode == "RGB"

    def test_jpeg_input(self):
        """JPEG 輸入也能正常處理。"""
        img = Image.new("RGB", (500, 500), color="blue")
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=95)
        result = compress_image_bytes(buf.getvalue())
        out = Image.open(BytesIO(result))
        assert out.format == "JPEG"

    def test_webp_input(self):
        """WebP 輸入也能正常處理。"""
        img = Image.new("RGB", (500, 500), color="green")
        buf = BytesIO()
        img.save(buf, format="WEBP")
        result = compress_image_bytes(buf.getvalue())
        out = Image.open(BytesIO(result))
        assert out.format == "JPEG"

    def test_invalid_input_raises(self):
        """非圖片位元組丟擲 ValueError。"""
        with pytest.raises(ValueError, match="Invalid image"):
            compress_image_bytes(b"not an image")

    def test_output_smaller_than_input(self):
        """壓縮後體積應顯著減小。"""
        raw = self._make_png(3000, 2000)
        result = compress_image_bytes(raw)
        assert len(result) < len(raw)
