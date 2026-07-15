from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.auto_publish import (
    AUTO_PUBLISH_PAYLOADS,
    AUTO_PUBLISH_TASKS,
    _create_publish_task,
    execute_auto_publish_retry,
    retry_auto_publish_item,
)
from app.models import AutoPublishCreate


class AutoPublishTest(unittest.TestCase):
    def tearDown(self) -> None:
        AUTO_PUBLISH_TASKS.clear()
        AUTO_PUBLISH_PAYLOADS.clear()

    def test_auto_publish_uses_deterministic_concat_by_default(self) -> None:
        payload = AutoPublishCreate(drama_names=["测试短剧"])

        self.assertEqual(payload.pipeline_template_key, "episode_concat_visual")

    def test_create_publish_task_passes_kuaishou_author_service_fields(self) -> None:
        payload = AutoPublishCreate(
            drama_names=["测试短剧"],
            platform="kuaishou",
            account_ids=["kuaishou:main"],
            kuaishou_enable_promotion_task=True,
        )

        with patch("app.auto_publish.httpx.post") as post:
            post.return_value.raise_for_status.return_value = None
            post.return_value.json.return_value = {"id": "publish-1"}
            result = _create_publish_task(payload, title="测试短剧", file_paths=["/tmp/demo.mp4"])

        self.assertEqual(result["id"], "publish-1")
        body = post.call_args.kwargs["json"]
        self.assertEqual(body["platform"], "kuaishou")
        self.assertEqual(body["accountIds"], ["kuaishou:main"])
        self.assertTrue(body["kuaishouEnablePromotionTask"])
        self.assertEqual(body["kuaishouPromotionTaskTitle"], "测试短剧")

    def test_create_publish_task_omits_kuaishou_author_service_title_when_disabled(self) -> None:
        payload = AutoPublishCreate(
            drama_names=["测试短剧"],
            platform="kuaishou",
            account_ids=["kuaishou:main"],
            kuaishou_enable_promotion_task=False,
        )

        with patch("app.auto_publish.httpx.post") as post:
            post.return_value.raise_for_status.return_value = None
            post.return_value.json.return_value = {"id": "publish-1"}
            _create_publish_task(payload, title="测试短剧", file_paths=["/tmp/demo.mp4"])

        body = post.call_args.kwargs["json"]
        self.assertNotIn("kuaishouPromotionTaskTitle", body)

    def test_retry_reuses_completed_stages_and_only_retries_publish(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            downloaded = Path(tmp_dir) / "episode.mp4"
            asset = Path(tmp_dir) / "final.mp4"
            downloaded.touch()
            asset.touch()
            payload = AutoPublishCreate(
                drama_names=["测试短剧"],
                account_ids=["kuaishou:main"],
            )
            AUTO_PUBLISH_PAYLOADS["task-1"] = payload
            AUTO_PUBLISH_TASKS["task-1"] = {
                "id": "task-1",
                "status": "failed",
                "message": "发布失败",
                "progress": 100,
                "total": 1,
                "completed": 1,
                "logs": [],
                "items": [{
                    "name": "测试短剧",
                    "status": "failed",
                    "progress": 100,
                    "error": "发布失败",
                    "resource": {"drama_name": "测试短剧", "baidu_url": "https://example.test", "extract_code": "1234"},
                    "project_id": 9,
                    "downloaded": [{"local_path": str(downloaded)}],
                    "video_ids": [12],
                    "asset_paths": [str(asset)],
                }],
            }

            retry_auto_publish_item("task-1", 0)
            with (
                patch("app.auto_publish.qingque_resource_client.search") as search,
                patch("app.auto_publish.download_first_episodes_from_baidupcs_share") as download,
                patch("app.auto_publish.compose_episode_publish_video") as compose,
                patch("app.auto_publish._create_publish_task", return_value={"id": "publish-2"}) as publish,
                patch("app.auto_publish._wait_publish_task"),
                patch("app.auto_publish._record_published"),
            ):
                execute_auto_publish_retry("task-1", 0)

        search.assert_not_called()
        download.assert_not_called()
        compose.assert_not_called()
        publish.assert_called_once_with(payload, title="测试短剧", file_paths=[str(asset)])
        self.assertEqual(AUTO_PUBLISH_TASKS["task-1"]["items"][0]["status"], "succeeded")
        self.assertEqual(AUTO_PUBLISH_TASKS["task-1"]["status"], "succeeded")


if __name__ == "__main__":
    unittest.main()
