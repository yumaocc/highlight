from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sau_backend


class PublishNoteApiTest(unittest.TestCase):
    def test_publish_note_creates_note_task(self) -> None:
        with patch("sau_backend.threading.Thread") as thread:
            response = sau_backend.app.test_client().post(
                "/api/publish/note",
                json={
                    "platform": "xiaohongshu",
                    "accountIds": ["xiaohongshu:main"],
                    "imagePaths": ["/tmp/promotion.png"],
                    "title": "测试标题",
                    "content": "测试正文",
                    "topics": ["推广"],
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["platform"], "xiaohongshu")
        self.assertEqual(thread.call_args.kwargs["target"], sau_backend._run_publish_task)
        task_args = thread.call_args.kwargs["args"]
        self.assertEqual(task_args[2]["contentType"], "note")
        self.assertEqual(task_args[2]["description"], "测试正文")

    def test_run_publish_task_uses_upload_note_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            image = Path(tmp_dir) / "promotion.png"
            image.touch()
            task_id = "note-task"
            sau_backend.publish_tasks[task_id] = {"id": task_id, "status": "pending", "logs": []}
            payload = {
                "contentType": "note",
                "imagePaths": [str(image)],
                "title": "测试标题",
                "description": "测试正文",
                "topics": ["推广", "新品"],
            }
            with patch("sau_backend.subprocess.run") as run:
                run.return_value.returncode = 0
                run.return_value.stdout = "ok"
                run.return_value.stderr = ""
                sau_backend._run_publish_task(task_id, "xiaohongshu", payload, ["main"])

        command = run.call_args.args[0]
        self.assertIn("upload-note", command)
        self.assertIn("--images", command)
        self.assertIn("--note", command)
        self.assertNotIn("upload-video", command)
        self.assertEqual(sau_backend.publish_tasks[task_id]["status"], "succeeded")


if __name__ == "__main__":
    unittest.main()
