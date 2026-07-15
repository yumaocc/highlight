from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from app.auto_compose import _build_contact_sheet, _generate_visual, _natural_sort_paths, compose_episode_publish_video


class AutoComposeTest(unittest.TestCase):
    def test_natural_sort_orders_episode_numbers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            paths = [root / "第10集.mp4", root / "第2集.mp4", root / "第1集.mp4"]
            for path in paths:
                path.touch()
            result = _natural_sort_paths(paths)
        self.assertEqual([path.name for path in result], ["第1集.mp4", "第2集.mp4", "第10集.mp4"])

    def test_contact_sheet_combines_reference_frames(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            frames = []
            for index in range(3):
                path = root / f"frame_{index}.jpg"
                Image.new("RGB", (100, 180), (index * 50, 20, 30)).save(path)
                frames.append(path)
            output = root / "sheet.jpg"
            _build_contact_sheet(frames, output)
            with Image.open(output) as image:
                self.assertEqual(image.size, (1080, 1440))

    def test_visual_generation_failure_uses_local_reference_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            reference = root / "reference.jpg"
            output = root / "outro.png"
            Image.new("RGB", (1080, 1440), "navy").save(reference)
            with patch(
                "app.auto_compose.generate_short_drama_template_visual",
                return_value={"ok": False, "error": "HTTP 524"},
            ):
                result = _generate_visual("outro", "测试短剧", reference, output, 3.0)

            self.assertTrue(output.is_file())
            self.assertEqual(result["mode"], "local_reference_fallback")
            self.assertEqual(result["generation_error"], "HTTP 524")

    def test_compose_trims_generates_visuals_and_concatenates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            sources = [root / "第2集.mp4", root / "第1集.mp4"]
            for source in sources:
                source.touch()

            def fake_frame(_source: Path, output: Path, _timestamp: float) -> None:
                Image.new("RGB", (360, 640), "navy").save(output)

            def fake_visual(*_args, **kwargs):
                Image.new("RGB", (360, 640), "red").save(kwargs["output_path"])
                return {"ok": True, "model": "gpt-image-2"}

            def fake_media_output(*args, **_kwargs):
                output = args[1]
                output.parent.mkdir(parents=True, exist_ok=True)
                output.touch()

            fake_settings = type("Settings", (), {
                "work_dir": root / "work",
                "promo_dir": root / "promos",
            })()
            with (
                patch("app.auto_compose.get_settings", return_value=fake_settings),
                patch("app.auto_compose.probe_video", return_value={"duration": 20.0}),
                patch("app.auto_compose.extract_frame_image", side_effect=fake_frame),
                patch("app.auto_compose.generate_short_drama_template_visual", side_effect=fake_visual) as visual,
                patch("app.auto_compose.render_clip_segment", side_effect=fake_media_output) as trim,
                patch("app.auto_compose.render_image_segment", side_effect=fake_media_output),
                patch("app.auto_compose.concat_video_segments", side_effect=fake_media_output) as concat,
                patch("app.auto_compose.record_generated_asset", return_value={"id": 7, "output_path": "final.mp4"}),
            ):
                result = compose_episode_publish_video(
                    project_id=3,
                    drama_name="测试短剧",
                    source_paths=sources,
                )

        self.assertEqual(trim.call_count, 2)
        self.assertEqual(visual.call_count, 2)
        for call in visual.call_args_list:
            self.assertIsNone(call.kwargs.get("reference_image_path"))
            self.assertEqual(call.kwargs["timeout_seconds"], 180)
            self.assertEqual(call.kwargs["attempts"], 2)
            self.assertTrue(call.kwargs["compact_prompt"])
        self.assertEqual(concat.call_count, 1)
        self.assertEqual(result["metadata"]["pipeline"], "episode_concat_visual")


if __name__ == "__main__":
    unittest.main()
