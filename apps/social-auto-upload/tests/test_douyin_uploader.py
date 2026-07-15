import asyncio
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from uploader.douyin_uploader.main import DouYinVideo


class _FakeLocator:
    def __init__(self, text: str):
        self.text = text

    async def inner_text(self, timeout=None):
        return self.text


class _FakePage:
    def __init__(self, text: str):
        self.text = text

    def locator(self, selector: str):
        return _FakeLocator(self.text)


class DouYinVideoPublishTests(unittest.TestCase):
    def make_uploader(self) -> DouYinVideo:
        return DouYinVideo(
            title="测试标题",
            file_path=Path("videos/demo.mp4"),
            tags=[],
            publish_date=0,
            account_file=Path("cookies/douyin_main.json"),
            debug=False,
        )

    def test_visible_publish_blockers_extracts_page_markers(self):
        uploader = self.make_uploader()
        page = _FakePage("快速检测 检测中7% 横/竖双封面缺失 请选择自主声明")

        blockers = asyncio.run(uploader.get_visible_publish_blockers(page))

        self.assertIn("检测中", blockers)
        self.assertIn("横/竖双封面缺失", blockers)
        self.assertIn("请选择自主声明", blockers)

    def test_wait_for_publish_ready_allows_cover_advice_after_detection(self):
        uploader = self.make_uploader()
        page = _FakePage("横/竖双封面缺失")
        uploader.dismiss_publish_overlays = AsyncMock()
        uploader.set_self_declaration = AsyncMock(return_value=True)

        asyncio.run(uploader.wait_for_publish_ready(page))

        uploader.dismiss_publish_overlays.assert_awaited()
        uploader.set_self_declaration.assert_awaited()


if __name__ == "__main__":
    unittest.main()
