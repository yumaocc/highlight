from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.main import (
    RESOURCE_IMPORT_TASKS,
    _execute_resource_import_task,
    _get_resource_import_task,
)
from app.models import ResourceImportCreate, ScanResult


class ResourceImportTaskTest(unittest.TestCase):
    def test_execute_resource_import_creates_pipeline_run(self) -> None:
        task_id = "test-resource-import"
        with tempfile.TemporaryDirectory() as tmp_dir:
            video_paths = [str(Path(tmp_dir) / f"第{index}集.mp4") for index in range(1, 6)]
            RESOURCE_IMPORT_TASKS[task_id] = {
                "id": task_id,
                "status": "pending",
                "progress": 0,
                "message": "",
                "downloaded": [],
                "selected": [],
                "scan": None,
                "video_ids": [],
                "pipeline_runs": [],
                "logs": [],
            }
            payload = ResourceImportCreate(project_id=7, baidu_url="https://pan.baidu.com/s/example", extract_code="abcd", episode_limit=5)

            with (
                patch(
                    "app.main.download_first_episodes_from_baidupcs_share",
                    return_value={
                        "selected": [{"name": f"第{index}集.mp4", "remote_path": f"/短剧资源/第{index}集.mp4"} for index in range(1, 6)],
                        "downloaded": [
                            {
                                "name": f"第{index}集.mp4",
                                "remote_path": f"/短剧资源/第{index}集.mp4",
                                "local_path": video_paths[index - 1],
                                "size_bytes": 9,
                                "episode_number": index,
                            }
                            for index in range(1, 6)
                        ],
                    },
                ),
                patch("app.main.scan_videos", return_value=ScanResult(indexed=5, failed=[])),
                patch("app.main._video_ids_for_paths", return_value=[101, 102, 103, 104, 105]),
                patch(
                    "app.main.create_pipeline_runs",
                    return_value={"runs": [{"id": 201, "status": "pending", "template_key": "story_quality_cut"}]},
                ) as create_pipeline_runs,
            ):
                _execute_resource_import_task(task_id, payload)

            task = _get_resource_import_task(task_id)
            self.assertEqual(task["status"], "succeeded")
            self.assertEqual(task["video_ids"], [101, 102, 103, 104, 105])
            self.assertEqual(task["pipeline_runs"][0]["id"], 201)
            create_pipeline_runs.assert_called_once()

        RESOURCE_IMPORT_TASKS.pop(task_id, None)


if __name__ == "__main__":
    unittest.main()
