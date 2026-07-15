from __future__ import annotations

import unittest

from app.qingque_resource import (
    QingqueResourceClient,
    extract_code,
    extract_resources_from_rows,
    parse_snapshot_rows,
)


class QingqueResourceTest(unittest.TestCase):
    def test_parse_snapshot_rows(self) -> None:
        snapshot = [
            [10000035, {}],
            [
                10000050,
                {
                    "2": {
                        "2": [
                            {"1": 0, "2": 0, "3": 0},
                            {"1": 0, "2": 1, "3": 1},
                            {"1": 1, "2": 0, "3": 2},
                            {"1": 1, "2": 1, "3": 3},
                        ],
                        "3": [{"1": 0}, {"1": 1}, {"1": 2}, {"1": 3}],
                        "4": [
                            {"1": 2, "2": "任务名称"},
                            {"1": 2, "2": "网盘链接"},
                            {"1": 2, "2": "爱在阳光下"},
                            {"1": 2, "2": "https://pan.baidu.com/s/example?pwd=abcd"},
                        ],
                    }
                },
            ],
        ]

        rows = parse_snapshot_rows(snapshot)

        self.assertEqual(rows[0][0], "任务名称")
        self.assertEqual(rows[1][1], "https://pan.baidu.com/s/example?pwd=abcd")

    def test_extract_resources_from_rows(self) -> None:
        rows = {
            1: {0: "短剧id", 1: "任务名称", 5: "网盘链接"},
            2: {0: 1, 1: "爱在阳光下", 5: "https://pan.baidu.com/s/abc 提取码: qtys"},
        }

        resources = extract_resources_from_rows(rows, sheet_id="sheet1", sheet_name="资源表")

        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0].drama_name, "爱在阳光下")
        self.assertEqual(resources[0].baidu_url, "https://pan.baidu.com/s/abc")
        self.assertEqual(resources[0].extract_code, "qtys")
        self.assertEqual(resources[0].row, 3)

    def test_extract_code_from_pwd_query_first(self) -> None:
        self.assertEqual(extract_code("https://pan.baidu.com/s/abc?pwd=8888 提取码: qtys", "https://pan.baidu.com/s/abc?pwd=8888"), "8888")

    def test_search_uses_cached_resources(self) -> None:
        client = QingqueResourceClient()
        client._cache = [
            extract_resources_from_rows(
                {1: {1: "任务名称", 5: "网盘链接"}, 2: {1: "爱在阳光下", 5: "https://pan.baidu.com/s/abc?pwd=8888"}},
                sheet_id="sheet1",
                sheet_name="资源表",
            )[0]
        ]
        client._cache_expires_at = 999999999

        matches = client.search("阳光", limit=5)

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].drama_name, "爱在阳光下")
        self.assertEqual(matches[0].match_type, "contains")


if __name__ == "__main__":
    unittest.main()
