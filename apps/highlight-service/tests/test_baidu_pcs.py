from __future__ import annotations

import tempfile
import unittest
import json
import os
from pathlib import Path
from unittest.mock import patch

from app.baidu_pcs import (
    BaiduPCSClient,
    _CommandResult,
    _extract_bdstoken,
    _extract_yun_data,
    _load_baidupcs_cookies,
    download_first_episodes_from_baidupcs_share,
    parse_ls_output,
    parse_size,
)
from app.episode_selector import RemoteFile, episode_number, select_first_episodes


class FakeBaiduPCSClient(BaiduPCSClient):
    def __init__(self) -> None:
        self.binary_path = "fake"
        self.timeout_seconds = 60
        self.calls: list[tuple] = []
        self.files = [
            RemoteFile("目标剧-第03集.mp4", "/短剧资源/目标剧/目标剧-第03集.mp4", 9),
            RemoteFile("目标剧-预告-第01集.mp4", "/短剧资源/目标剧/目标剧-预告-第01集.mp4", 9),
            RemoteFile("目标剧-第01集.mp4", "/短剧资源/目标剧/目标剧-第01集.mp4", 9),
            RemoteFile("目标剧-第02集.mp4", "/短剧资源/目标剧/目标剧-第02集.mp4", 9),
            RemoteFile("目标剧-第04集.mp4", "/短剧资源/目标剧/目标剧-第04集.mp4", 9),
            RemoteFile("目标剧-第05集.mp4", "/短剧资源/目标剧/目标剧-第05集.mp4", 9),
            RemoteFile("目标剧-第06集.mp4", "/短剧资源/目标剧/目标剧-第06集.mp4", 9),
        ]

    def transfer_share(self, share_url: str, extract_code: str = "", target_dir: str = "/") -> dict:
        self.calls.append(("transfer_share", share_url, extract_code, target_dir))
        return {"target_dir": target_dir, "output": "转存成功"}

    def list_video_files(self, remote_dir: str, *, recursive: bool = True, max_depth: int = 4) -> list[RemoteFile]:
        self.calls.append(("list_video_files", remote_dir, recursive, max_depth))
        return self.files

    def download_file(self, remote_file: RemoteFile, destination_dir: Path, *, overwrite: bool = False):
        self.calls.append(("download_file", remote_file.path, str(destination_dir), overwrite))
        destination_dir.mkdir(parents=True, exist_ok=True)
        target = destination_dir / remote_file.name
        target.write_bytes(remote_file.name.encode("utf-8"))
        from app.episode_selector import DownloadedEpisode

        return DownloadedEpisode(
            name=remote_file.name,
            remote_path=remote_file.path,
            local_path=str(target),
            size_bytes=target.stat().st_size,
            episode_number=episode_number(remote_file.name),
        )


class BaiduPCSTest(unittest.TestCase):
    def test_transfer_share_uses_saas_fallback_for_misleading_stoken_error(self) -> None:
        client = BaiduPCSClient.__new__(BaiduPCSClient)
        client.binary_path = "fake"
        client.timeout_seconds = 60
        error = "分享链接转存到网盘失败: 请确认登录参数中已经包含了网盘STOKEN"
        with (
            patch.object(client, "mkdirs"),
            patch.object(client, "cd"),
            patch.object(client, "_run", return_value=_CommandResult(0, error)),
            patch("app.baidu_pcs.transfer_saas_share", return_value={
                "ok": True,
                "skipped": False,
                "reason": "saas_fallback",
                "message": "企业分享转存成功",
            }) as fallback,
        ):
            result = client.transfer_share("https://pan.baidu.com/s/example", "abcd", "/目标剧")

        fallback.assert_called_once_with("https://pan.baidu.com/s/example", "abcd", "/目标剧")
        self.assertEqual(result["reason"], "saas_fallback")

    def test_load_baidupcs_cookies_removes_stale_and_invalid_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = {
                "baidu_active_uid": 1,
                "baidu_user_list": [{
                    "uid": 1,
                    "cookies": 'BDUSS=bduss; STOKEN=stoken; BDCLND=stale; RT="invalid"',
                }],
            }
            Path(tmp_dir, "pcs_config.json").write_text(json.dumps(config), encoding="utf-8")
            with patch.dict(os.environ, {"BAIDUPCS_GO_CONFIG_DIR": tmp_dir}):
                cookies = _load_baidupcs_cookies()

        self.assertEqual(cookies, {"BDUSS": "bduss", "STOKEN": "stoken"})

    def test_extract_saas_page_data_and_bdstoken(self) -> None:
        data = _extract_yun_data('<script>window.yunData = {"shareType":"saas"};\n</script>')

        self.assertEqual(data["shareType"], "saas")
        self.assertEqual(_extract_bdstoken('{"bdstoken":"token-value"}'), "token-value")

    def test_episode_number_patterns(self) -> None:
        self.assertEqual(episode_number("短剧-第01集.mp4"), 1)
        self.assertEqual(episode_number("Drama EP05.mp4"), 5)
        self.assertEqual(episode_number("S01E12.mp4"), 12)
        self.assertEqual(episode_number("3.mp4"), 3)
        self.assertIsNone(episode_number("花絮.mp4"))

    def test_select_first_episodes_prefers_story_files_for_target_drama(self) -> None:
        files = [
            RemoteFile("目标剧-第03集.mp4", "/合集/目标剧/目标剧-第03集.mp4"),
            RemoteFile("目标剧-预告-第01集.mp4", "/合集/目标剧/目标剧-预告-第01集.mp4"),
            RemoteFile("其他剧-第01集.mp4", "/合集/其他剧/其他剧-第01集.mp4"),
            RemoteFile("目标剧-第01集.mp4", "/合集/目标剧/目标剧-第01集.mp4"),
            RemoteFile("目标剧-花絮-第02集.mp4", "/合集/目标剧/目标剧-花絮-第02集.mp4"),
            RemoteFile("目标剧-第05集.mp4", "/合集/目标剧/目标剧-第05集.mp4"),
            RemoteFile("目标剧-第02集.mp4", "/合集/目标剧/目标剧-第02集.mp4"),
            RemoteFile("目标剧-第04集.mp4", "/合集/目标剧/目标剧-第04集.mp4"),
            RemoteFile("目标剧-第06集.mp4", "/合集/目标剧/目标剧-第06集.mp4"),
        ]

        selected = select_first_episodes(files, limit=5, drama_name="目标剧")

        self.assertEqual(
            [item.name for item in selected],
            ["目标剧-第01集.mp4", "目标剧-第02集.mp4", "目标剧-第03集.mp4", "目标剧-第04集.mp4", "目标剧-第05集.mp4"],
        )

    def test_select_first_episodes_uses_remote_dir_name_when_files_do_not_include_title(self) -> None:
        files = [
            RemoteFile("第03集.mp4", "/合集/目标剧/第03集.mp4"),
            RemoteFile("第01集.mp4", "/合集/其他剧/第01集.mp4"),
            RemoteFile("第01集.mp4", "/合集/目标剧/第01集.mp4"),
            RemoteFile("第02集.mp4", "/合集/目标剧/第02集.mp4"),
        ]

        selected = select_first_episodes(files, limit=2, drama_name="目标剧")

        self.assertEqual([item.path for item in selected], ["/合集/目标剧/第01集.mp4", "/合集/目标剧/第02集.mp4"])

    def test_parse_ls_output(self) -> None:
        output = """
当前目录: /短剧资源/目标剧
----
   #    文件大小        修改日期                文件(目录)
    0           -  2026-01-01 17:29:00  子目录/
    1     19.96MB  2026-02-05 18:23:17  第01集.mp4
    2    191.72KB  2026-02-05 18:17:48  封面.jpg
       总: 20.15MB                       文件总数: 2, 目录总数: 1
"""
        files = parse_ls_output(output, "/短剧资源/目标剧")

        self.assertEqual(len(files), 3)
        self.assertTrue(files[0].is_dir)
        self.assertEqual(files[0].path, "/短剧资源/目标剧/子目录")
        self.assertEqual(files[1].name, "第01集.mp4")
        self.assertEqual(files[1].size, parse_size("19.96MB"))

    def test_download_first_episodes_from_baidupcs_share(self) -> None:
        client = FakeBaiduPCSClient()
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = download_first_episodes_from_baidupcs_share(
                "https://pan.baidu.com/s/example",
                "abcd",
                Path(tmp_dir),
                remote_root="/短剧资源",
                remote_name="目标剧",
                limit=5,
                drama_name="目标剧",
                client=client,
            )

        self.assertEqual(result["remote_dir"], "/短剧资源/目标剧")
        self.assertEqual([item["episode_number"] for item in result["downloaded"]], [1, 2, 3, 4, 5])
        self.assertEqual(client.calls[0], ("transfer_share", "https://pan.baidu.com/s/example", "abcd", "/短剧资源/目标剧"))


if __name__ == "__main__":
    unittest.main()
