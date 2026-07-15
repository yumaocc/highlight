import asyncio
import unittest
from unittest.mock import AsyncMock

from uploader.ks_uploader.main import KSVideo


class KuaishouVideoPublishTests(unittest.TestCase):
    def make_uploader(self) -> KSVideo:
        return KSVideo(
            title="测试标题",
            file_path="videos/demo.mp4",
            tags=[],
            publish_date=0,
            account_file="cookies/kuaishou_main.json",
            promotion_task_title="测试变现任务",
            debug=False,
        )

    def test_promotion_task_failure_stops_publish_flow(self):
        uploader = self.make_uploader()
        uploader.set_promotion_task = AsyncMock(side_effect=RuntimeError("dropdown missing"))

        with self.assertRaisesRegex(RuntimeError, "快手变现任务关联失败，已停止发布"):
            asyncio.run(uploader.try_set_promotion_task(object()))

        uploader.set_promotion_task.assert_awaited_once()

    def test_promotion_task_title_normalization(self):
        self.assertEqual(KSVideo._normalize_dropdown_text("  A\n  B   C  "), "A B C")

    def test_promotion_task_title_candidates_strip_publish_suffix(self):
        self.assertEqual(
            KSVideo._promotion_task_title_candidates("秀芬的遗嘱 剧情精剪")[:2],
            ["秀芬的遗嘱 剧情精剪", "秀芬的遗嘱"],
        )

    def test_promotion_task_title_candidates_keep_numbered_title(self):
        self.assertIn("上海滩风云1", KSVideo._promotion_task_title_candidates("上海滩风云1 剧情精剪"))

    def test_promotion_task_dom_fallback_runs_without_dropdown_locator(self):
        uploader = self.make_uploader()
        page = object()
        task_select = object()
        uploader._try_open_ant_select = AsyncMock(return_value=None)
        uploader._fill_ant_select_search = AsyncMock()
        uploader._visible_ant_dropdown = AsyncMock(side_effect=RuntimeError("dropdown hidden"))
        uploader._click_dropdown_option_from_page_dom = AsyncMock(return_value=True)

        selected = asyncio.run(uploader._select_promotion_task_option(page, task_select, "秀芬的遗嘱"))

        self.assertTrue(selected)
        uploader._click_dropdown_option_from_page_dom.assert_awaited_with(page, "秀芬的遗嘱", "变现任务")


if __name__ == "__main__":
    unittest.main()
