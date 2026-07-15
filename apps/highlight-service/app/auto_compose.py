from __future__ import annotations

import hashlib
import random
import re
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps

from .ai_clients import generate_short_drama_template_visual
from .config import get_settings
from .ffmpeg import (
    concat_video_segments,
    extract_frame_image,
    probe_video,
    render_clip_segment,
    render_image_segment,
)
from .projects import record_generated_asset


DEFAULT_TRIM_SECONDS = 1.5
DEFAULT_REFERENCE_FRAME_COUNT = 6
INTRO_DURATION_SECONDS = 2.5
OUTRO_DURATION_SECONDS = 3.0


def compose_episode_publish_video(
    *,
    project_id: int,
    drama_name: str,
    source_paths: list[str | Path],
    trim_start_seconds: float = DEFAULT_TRIM_SECONDS,
    trim_end_seconds: float = DEFAULT_TRIM_SECONDS,
    reference_frame_count: int = DEFAULT_REFERENCE_FRAME_COUNT,
) -> dict[str, Any]:
    sources = _natural_sort_paths(source_paths)
    if not sources:
        raise RuntimeError("没有可合成的剧情视频")

    settings = get_settings()
    work_dir = settings.work_dir / "auto-compose" / f"project_{project_id}"
    segment_dir = work_dir / "episodes"
    reference_dir = work_dir / "references"
    visual_dir = work_dir / "visuals"
    for directory in (segment_dir, reference_dir, visual_dir, settings.promo_dir):
        directory.mkdir(parents=True, exist_ok=True)

    trimmed_segments: list[Path] = []
    source_details: list[dict[str, Any]] = []
    for index, source in enumerate(sources, start=1):
        probe = probe_video(source)
        duration = float(probe.get("duration") or 0)
        start = max(0.0, float(trim_start_seconds))
        end = duration - max(0.0, float(trim_end_seconds))
        if end <= start + 0.5:
            raise RuntimeError(f"视频过短，无法裁掉片头片尾：{source.name}（{duration:.2f} 秒）")
        output = segment_dir / f"episode_{index:03d}.mp4"
        if not output.is_file() or output.stat().st_size <= 0:
            render_clip_segment(source, output, start, end)
        trimmed_segments.append(output)
        source_details.append({
            "path": str(source),
            "duration": duration,
            "trim_start": start,
            "trim_end": max(0.0, duration - end),
            "kept_duration": end - start,
        })

    reference_frames = _extract_random_reference_frames(
        sources,
        reference_dir,
        drama_name=drama_name,
        count=reference_frame_count,
        trim_start_seconds=trim_start_seconds,
        trim_end_seconds=trim_end_seconds,
    )
    contact_sheet = reference_dir / "reference_contact_sheet.jpg"
    _build_contact_sheet(reference_frames, contact_sheet)

    intro_image = visual_dir / "intro.png"
    outro_image = visual_dir / "outro.png"
    intro_result = (
        {"ok": True, "kind": "intro", "mode": "reused", "output_path": str(intro_image)}
        if intro_image.is_file() and intro_image.stat().st_size > 0
        else _generate_visual("intro", drama_name, contact_sheet, intro_image, INTRO_DURATION_SECONDS)
    )
    outro_result = (
        {"ok": True, "kind": "outro", "mode": "reused", "output_path": str(outro_image)}
        if outro_image.is_file() and outro_image.stat().st_size > 0
        else _generate_visual("outro", drama_name, contact_sheet, outro_image, OUTRO_DURATION_SECONDS)
    )

    intro_segment = visual_dir / "intro.mp4"
    outro_segment = visual_dir / "outro.mp4"
    render_image_segment(intro_image, intro_segment, INTRO_DURATION_SECONDS)
    render_image_segment(outro_image, outro_segment, OUTRO_DURATION_SECONDS)

    safe_name = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "_", drama_name).strip("_") or f"project_{project_id}"
    final_output = settings.promo_dir / f"auto_concat_{project_id}_{safe_name}.mp4"
    concat_video_segments([intro_segment, *trimmed_segments, outro_segment], final_output)
    final_duration = sum(item["kept_duration"] for item in source_details) + INTRO_DURATION_SECONDS + OUTRO_DURATION_SECONDS
    metadata = {
        "pipeline": "episode_concat_visual",
        "sources": source_details,
        "reference_frames": [str(path) for path in reference_frames],
        "reference_contact_sheet": str(contact_sheet),
        "intro": intro_result,
        "outro": outro_result,
        "trim_start_seconds": trim_start_seconds,
        "trim_end_seconds": trim_end_seconds,
    }
    asset = record_generated_asset(
        project_id=project_id,
        asset_type="episode_concat_visual",
        title=f"{drama_name} 自动拼接成片",
        description="逐集裁剪首尾后拼接，并加入 GPT Image 2 生成的片头片尾",
        output_path=final_output,
        download_url=f"/api/promo-files/{final_output.name}/download",
        duration=final_duration,
        metadata=metadata,
    )
    return {**asset, "metadata": metadata}


def _generate_visual(kind: str, drama_name: str, reference: Path, output: Path, duration: float) -> dict[str, Any]:
    if kind == "intro":
        brief = (
            "参考图是一组从本剧不同集数随机抽取的真实画面。综合判断主要人物、服装、场景和情绪，"
            "选择最有冲突感的一组人物关系制作片头；保持角色辨识度，不要照搬拼图布局。"
        )
        style = "短剧强冲突片头、真实人物一致性、电影感竖屏视觉"
    else:
        brief = (
            "参考图是一组从本剧随机抽取的真实画面。延续片中人物和氛围制作有悬念的片尾，"
            "清楚引导点击左下角观看全集，不要生成与本剧无关的通用人物。"
        )
        style = "短剧悬念片尾、人物一致、清晰观看全集动线"
    result = generate_short_drama_template_visual(
        kind=kind,
        drama_name=drama_name,
        style=style,
        brief=brief,
        duration=max(1, round(duration)),
        output_path=output,
        image_model="gpt-image-2",
        timeout_seconds=180,
        attempts=2,
        compact_prompt=True,
    )
    if not result.get("ok") or not output.is_file():
        error = result.get("error") or "没有输出图片"
        _render_local_visual_fallback(kind, drama_name, reference, output)
        return {
            "ok": True,
            "kind": kind,
            "mode": "local_reference_fallback",
            "model": "local-pillow",
            "output_path": str(output),
            "generation_error": error,
        }
    return result


def _render_local_visual_fallback(kind: str, drama_name: str, reference: Path, output: Path) -> None:
    with Image.open(reference) as source:
        image = ImageOps.fit(source.convert("RGB"), (1080, 1920), method=Image.Resampling.LANCZOS)
    image = ImageEnhance.Brightness(image).enhance(0.58)
    draw = ImageDraw.Draw(image, "RGBA")
    draw.rectangle((0, 0, 1080, 1920), fill=(0, 0, 0, 45))
    font_path = _visual_font_path()
    title_font = ImageFont.truetype(font_path, 76)
    subtitle_font = ImageFont.truetype(font_path, 54)
    if kind == "intro":
        lines = [drama_name[:16], drama_name[16:32]] if len(drama_name) > 16 else [drama_name]
        y = 140
        for line in lines:
            _draw_centered_text(draw, line, y, title_font)
            y += 98
    else:
        _draw_centered_text(draw, "点击左下角", 1450, title_font)
        _draw_centered_text(draw, "观看全集", 1555, subtitle_font)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format="PNG")


def _draw_centered_text(draw: ImageDraw.ImageDraw, text: str, y: int, font: ImageFont.FreeTypeFont) -> None:
    box = draw.textbbox((0, 0), text, font=font, stroke_width=2)
    width = box[2] - box[0]
    draw.text(
        ((1080 - width) // 2, y),
        text,
        font=font,
        fill=(255, 255, 255, 255),
        stroke_width=2,
        stroke_fill=(0, 0, 0, 210),
    )


def _visual_font_path() -> str:
    candidates = (
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    )
    return next((path for path in candidates if Path(path).is_file()), "/System/Library/Fonts/Supplemental/Arial.ttf")


def _extract_random_reference_frames(
    sources: list[Path],
    output_dir: Path,
    *,
    drama_name: str,
    count: int,
    trim_start_seconds: float,
    trim_end_seconds: float,
) -> list[Path]:
    count = max(1, min(int(count), 12))
    seed = int.from_bytes(hashlib.sha256(drama_name.encode("utf-8")).digest()[:8], "big")
    rng = random.Random(seed)
    probes = [(source, probe_video(source)) for source in sources]
    selected: list[tuple[Path, float]] = []
    for index in range(count):
        source, probe = probes[index % len(probes)]
        duration = float(probe.get("duration") or 0)
        lower = min(max(0.0, trim_start_seconds + 1), max(0.0, duration * 0.25))
        upper = max(lower, duration - max(0.0, trim_end_seconds) - 1)
        selected.append((source, rng.uniform(lower, upper) if upper > lower else lower))

    frames: list[Path] = []
    for index, (source, timestamp) in enumerate(selected, start=1):
        output = output_dir / f"frame_{index:02d}.jpg"
        extract_frame_image(source, output, timestamp)
        frames.append(output)
    return frames


def _build_contact_sheet(frames: list[Path], output: Path) -> None:
    if not frames:
        raise RuntimeError("没有成功抽取 GPT Image 2 参考画面")
    columns = 2
    cell_width, cell_height = 540, 720
    rows = (len(frames) + columns - 1) // columns
    canvas = Image.new("RGB", (columns * cell_width, rows * cell_height), "black")
    draw = ImageDraw.Draw(canvas)
    for index, path in enumerate(frames):
        with Image.open(path) as source:
            image = source.convert("RGB")
            image.thumbnail((cell_width, cell_height))
            x = (index % columns) * cell_width + (cell_width - image.width) // 2
            y = (index // columns) * cell_height + (cell_height - image.height) // 2
            canvas.paste(image, (x, y))
            draw.text((index % columns * cell_width + 12, index // columns * cell_height + 12), str(index + 1), fill="white")
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format="JPEG", quality=90)


def _natural_sort_paths(paths: list[str | Path]) -> list[Path]:
    existing = [Path(path) for path in paths if Path(path).is_file()]

    def key(path: Path) -> list[tuple[int, Any]]:
        parts = re.split(r"(\d+)", path.name.lower())
        return [(0, int(part)) if part.isdigit() else (1, part) for part in parts]

    return sorted(existing, key=key)
