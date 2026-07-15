import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import sau_backend


class PublishApiTaskTests(unittest.TestCase):
    def setUp(self):
        sau_backend.publish_tasks.clear()
        self.client = sau_backend.app.test_client()

    def make_payload(self, file_path: Path):
        return {
            "platform": "douyin",
            "accountIds": ["douyin:creator"],
            "filePaths": [str(file_path)],
            "title": "测试发布",
            "description": "简介",
            "topics": ["#快来看短剧"],
            "isOriginal": True,
        }

    def wait_for_task(self, task_id: str, timeout: float = 2.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            response = self.client.get("/api/tasks")
            self.assertEqual(response.status_code, 200)
            tasks = response.get_json()
            task = next(item for item in tasks if item["id"] == task_id)
            if task["status"] not in {"pending", "running"}:
                return task
            time.sleep(0.02)
        self.fail(f"publish task {task_id} did not finish before timeout")

    def test_publish_video_task_marks_success_when_cli_succeeds(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            video_path = Path(tmp_dir) / "demo.mp4"
            video_path.write_bytes(b"video")

            with patch("sau_backend.subprocess.run", return_value=subprocess.CompletedProcess(["sau"], 0, "ok", "")) as mock_run:
                response = self.client.post("/api/publish/video", json=self.make_payload(video_path))
                self.assertEqual(response.status_code, 200)
                task = self.wait_for_task(response.get_json()["id"])

        self.assertEqual(task["status"], "succeeded")
        self.assertEqual(task["message"], "发布任务执行完成")
        command = mock_run.call_args.args[0]
        self.assertIn("--headed", command)
        self.assertNotIn("--headless", command)

    def test_publish_video_task_marks_failed_when_cli_times_out(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            video_path = Path(tmp_dir) / "demo.mp4"
            video_path.write_bytes(b"video")

            with patch("sau_backend._publish_task_timeout_seconds", return_value=1):
                with patch("sau_backend.subprocess.run", side_effect=subprocess.TimeoutExpired(["sau"], 1, output="still running")):
                    response = self.client.post("/api/publish/video", json=self.make_payload(video_path))
                    self.assertEqual(response.status_code, 200)
                    task = self.wait_for_task(response.get_json()["id"])

        self.assertEqual(task["status"], "failed")
        self.assertIn("发布子进程超时", task["message"])


if __name__ == "__main__":
    unittest.main()
