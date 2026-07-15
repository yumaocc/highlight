import json
import re
import subprocess
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFilter, ImageFont


VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"}


def parse_time(value: str) -> float:
    raw = value.strip()
    if not raw:
        raise ValueError("time value is empty")
    if re.fullmatch(r"\d+(\.\d+)?", raw):
        return float(raw)
    parts = raw.split(":")
    if len(parts) not in (2, 3):
        raise ValueError(f"unsupported time format: {value}")
    seconds = float(parts[-1])
    minutes = int(parts[-2])
    hours = int(parts[-3]) if len(parts) == 3 else 0
    return hours * 3600 + minutes * 60 + seconds


def format_time(seconds: float) -> str:
    total = max(0.0, seconds)
    hours = int(total // 3600)
    minutes = int((total % 3600) // 60)
    secs = total % 60
    return f"{hours:02d}-{minutes:02d}-{secs:05.2f}".replace(".", "_")


def discover_videos(input_dir: Path) -> list[Path]:
    if not input_dir.exists():
        input_dir.mkdir(parents=True, exist_ok=True)
    return sorted(
        path
        for path in input_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
    )


def probe_video(path: Path) -> dict:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    data = json.loads(result.stdout)
    video_stream = next(
        (stream for stream in data.get("streams", []) if stream.get("codec_type") == "video"),
        {},
    )
    fps = _parse_fps(video_stream.get("avg_frame_rate") or video_stream.get("r_frame_rate"))
    return {
        "duration": float(data.get("format", {}).get("duration") or 0),
        "width": int(video_stream.get("width") or 0),
        "height": int(video_stream.get("height") or 0),
        "fps": fps,
        "codec": video_stream.get("codec_name") or "",
    }


def cut_clip(source: Path, output: Path, start_seconds: float, end_seconds: float) -> None:
    if end_seconds <= start_seconds:
        raise ValueError("end time must be greater than start time")
    output.parent.mkdir(parents=True, exist_ok=True)
    duration = end_seconds - start_seconds
    command = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{start_seconds:.3f}",
        "-i",
        str(source),
        "-t",
        f"{duration:.3f}",
        "-c",
        "copy",
        "-avoid_negative_ts",
        "make_zero",
        str(output),
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)


def render_clip_segment(
    source: Path,
    output: Path,
    start_seconds: float,
    end_seconds: float,
) -> None:
    if end_seconds <= start_seconds:
        raise ValueError("end time must be greater than start time")
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{start_seconds:.3f}",
        "-i",
        str(source),
        "-t",
        f"{end_seconds - start_seconds:.3f}",
        "-vf",
        "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1",
        "-r",
        "30",
        "-pix_fmt",
        "yuv420p",
        "-c:v",
        "libx264",
        "-profile:v",
        "main",
        "-level",
        "4.1",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-c:a",
        "aac",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        str(output),
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)


def render_proxy_video(
    source: Path,
    output: Path,
    max_height: int = 480,
    fps: int = 12,
    video_bitrate: str = "650k",
    audio_bitrate: str = "48k",
) -> None:
    if max_height <= 0:
        raise ValueError("max_height must be greater than zero")
    if fps <= 0:
        raise ValueError("fps must be greater than zero")
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(source),
        "-vf",
        f"scale=-2:{max_height},setsar=1",
        "-r",
        str(fps),
        "-pix_fmt",
        "yuv420p",
        "-c:v",
        "libx264",
        "-profile:v",
        "main",
        "-preset",
        "veryfast",
        "-b:v",
        video_bitrate,
        "-maxrate",
        video_bitrate,
        "-bufsize",
        str(_double_bitrate(video_bitrate)),
        "-c:a",
        "aac",
        "-ar",
        "16000",
        "-ac",
        "1",
        "-b:a",
        audio_bitrate,
        "-movflags",
        "+faststart",
        str(output),
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)


def render_text_card(
    output: Path,
    title: str,
    subtitle: str = "",
    duration_seconds: float = 2.0,
    vertical_shift: int = 0,
    audio_path: Optional[Path] = None,
) -> None:
    if duration_seconds <= 0:
        raise ValueError("duration must be greater than zero")
    output.parent.mkdir(parents=True, exist_ok=True)
    image_path = output.with_suffix(".png")
    _render_card_image(image_path, title[:60], subtitle[:90], vertical_shift=vertical_shift)
    command = _animated_card_command(image_path, output, duration_seconds, audio_path=audio_path)
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    finally:
        image_path.unlink(missing_ok=True)


def render_masked_text_card(
    output: Path,
    source: Path,
    timestamp: float,
    title: str,
    subtitle: str = "",
    duration_seconds: float = 2.0,
    vertical_shift: int = 0,
    audio_path: Optional[Path] = None,
) -> None:
    if duration_seconds <= 0:
        raise ValueError("duration must be greater than zero")
    output.parent.mkdir(parents=True, exist_ok=True)
    image_path = output.with_suffix(".png")
    frame_path = output.with_suffix(".frame.jpg")
    try:
        extract_frame_image(source, frame_path, timestamp)
        _render_masked_card_image(image_path, frame_path, title[:60], subtitle[:90], vertical_shift=vertical_shift)
    except Exception:
        _render_card_image(image_path, title[:60], subtitle[:90], vertical_shift=vertical_shift)
    command = _animated_card_command(image_path, output, duration_seconds, audio_path=audio_path)
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    finally:
        image_path.unlink(missing_ok=True)
        frame_path.unlink(missing_ok=True)


def render_image_segment(
    image_path: Path,
    output: Path,
    duration_seconds: float = 2.0,
) -> None:
    if duration_seconds <= 0:
        raise ValueError("duration must be greater than zero")
    if not image_path.exists():
        raise FileNotFoundError(str(image_path))
    output.parent.mkdir(parents=True, exist_ok=True)
    command = _animated_card_command(image_path, output, duration_seconds)
    subprocess.run(command, check=True, capture_output=True, text=True)


def _animated_card_command(
    image_path: Path,
    output: Path,
    duration_seconds: float,
    audio_path: Optional[Path] = None,
) -> list[str]:
    fade_out_start = max(0.0, duration_seconds - 0.2)
    video_filter = (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        "setsar=1,"
        f"fade=t=out:st={fade_out_start:.3f}:d=0.20,"
        "format=yuv420p"
    )
    command = [
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-i",
        str(image_path),
    ]
    if audio_path and audio_path.exists():
        command.extend(["-i", str(audio_path)])
    else:
        command.extend([
            "-f",
            "lavfi",
            "-i",
            "anullsrc=channel_layout=stereo:sample_rate=44100",
        ])
    command.extend([
        "-t",
        f"{duration_seconds:.3f}",
        "-vf",
        video_filter,
        "-c:v",
        "libx264",
        "-profile:v",
        "main",
        "-level",
        "4.1",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-c:a",
        "aac",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-b:a",
        "128k",
        "-shortest",
        "-movflags",
        "+faststart",
        str(output),
    ])
    return command


def extract_frame_image(source: Path, output: Path, timestamp: float) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{max(0.0, timestamp):.3f}",
        "-i",
        str(source),
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(output),
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)


def concat_video_segments(segments: list[Path], output: Path) -> None:
    if not segments:
        raise ValueError("no segments to concatenate")
    output.parent.mkdir(parents=True, exist_ok=True)
    list_file = output.parent / f"{output.stem}_concat.txt"
    list_file.write_text(
        "\n".join(f"file '{path.resolve()}'" for path in segments),
        encoding="utf-8",
    )
    filters = []
    concat_inputs = []
    for index in range(len(segments)):
        filters.append(
            f"[{index}:v]"
            "scale=1080:1920:force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2,"
            "setsar=1,fps=30,format=yuv420p,setpts=PTS-STARTPTS"
            f"[v{index}]"
        )
        filters.append(
            f"[{index}:a]"
            "aformat=sample_rates=44100:channel_layouts=stereo,"
            "asetpts=PTS-STARTPTS"
            f"[a{index}]"
        )
        concat_inputs.append(f"[v{index}][a{index}]")
    filters.append("".join(concat_inputs) + f"concat=n={len(segments)}:v=1:a=1[v][a]")
    command = [
        "ffmpeg",
        "-y",
    ]
    for segment in segments:
        command.extend(["-i", str(segment)])
    command.extend([
        "-filter_complex",
        ";".join(filters),
        "-map",
        "[v]",
        "-map",
        "[a]",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-profile:v",
        "main",
        "-level",
        "4.1",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-c:a",
        "aac",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        str(output),
    ])
    subprocess.run(command, check=True, capture_output=True, text=True)


def _font_file() -> str:
    candidates = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return "/System/Library/Fonts/Supplemental/Arial.ttf"


def _render_card_image(path: Path, title: str, subtitle: str, vertical_shift: int = 0) -> None:
    image = Image.new("RGB", (1080, 1920), "#111827")
    draw = ImageDraw.Draw(image)
    title_font = ImageFont.truetype(_font_file(), 72)
    subtitle_font = ImageFont.truetype(_font_file(), 42)

    for index in range(0, 1920, 8):
        shade = int(17 + index / 1920 * 18)
        draw.line([(0, index), (1080, index)], fill=(shade, 24 + shade // 5, 39 + shade // 4), width=8)

    draw.rectangle((86, 570, 994, 1170), fill=(0, 0, 0, 92), outline=(15, 118, 110), width=4)
    _draw_centered_lines(draw, title, title_font, y=700 + vertical_shift, fill=(255, 255, 255), max_width=820, line_gap=18)
    if subtitle.strip():
        _draw_centered_lines(draw, subtitle, subtitle_font, y=1030 + vertical_shift, fill=(222, 235, 232), max_width=800, line_gap=12)
    image.save(path)


def _render_masked_card_image(path: Path, frame_path: Path, title: str, subtitle: str, vertical_shift: int = 0) -> None:
    background = Image.open(frame_path).convert("RGB")
    background = _cover_image(background, (1080, 1920))
    background = background.filter(ImageFilter.GaussianBlur(20))
    background = _darken_edges(background)

    overlay = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rectangle((0, 0, 1080, 1920), fill=(0, 0, 0, 108))
    draw.rounded_rectangle((72, 520, 1008, 1230), radius=28, fill=(0, 0, 0, 112))
    draw.rectangle((84, 520, 1008, 526), fill=(255, 255, 255, 42))

    image = Image.alpha_composite(background.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(image)
    title_font = ImageFont.truetype(_font_file(), 76)
    subtitle_font = ImageFont.truetype(_font_file(), 42)
    _draw_centered_lines(draw, title, title_font, y=760 + vertical_shift, fill=(255, 255, 255), max_width=820, line_gap=18)
    if subtitle.strip():
        _draw_centered_lines(draw, subtitle, subtitle_font, y=1050 + vertical_shift, fill=(232, 245, 242), max_width=800, line_gap=12)
    image.save(path)


def _cover_image(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    target_w, target_h = size
    source_w, source_h = image.size
    scale = max(target_w / source_w, target_h / source_h)
    resized = image.resize((int(source_w * scale), int(source_h * scale)), Image.Resampling.LANCZOS)
    left = (resized.width - target_w) // 2
    top = (resized.height - target_h) // 2
    return resized.crop((left, top, left + target_w, top + target_h))


def _darken_edges(image: Image.Image) -> Image.Image:
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for inset in range(0, 360, 12):
        alpha = int((360 - inset) / 360 * 9)
        draw.rectangle((inset, inset, image.width - inset, image.height - inset), outline=(0, 0, 0, alpha), width=12)
    return Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")


def _draw_centered_lines(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    y: int,
    fill: tuple[int, int, int],
    max_width: int,
    line_gap: int,
) -> None:
    lines = _wrap_text(draw, text.replace("\n", " ").strip(), font, max_width)
    total_height = sum(_text_size(draw, line, font)[1] for line in lines) + line_gap * max(0, len(lines) - 1)
    cursor_y = y - total_height // 2
    for line in lines:
        width, height = _text_size(draw, line, font)
        draw.text(((1080 - width) / 2, cursor_y), line, font=font, fill=fill)
        cursor_y += height + line_gap


def _wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
) -> list[str]:
    if not text:
        return []
    lines: list[str] = []
    current = ""
    for char in text:
        candidate = current + char
        if current and _text_size(draw, candidate, font)[0] > max_width:
            lines.append(current)
            current = char
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines[:3]


def _text_size(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def extract_audio_segment(
    source: Path,
    output: Path,
    start_seconds: float,
    end_seconds: float,
) -> None:
    if end_seconds <= start_seconds:
        raise ValueError("end time must be greater than start time")
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{start_seconds:.3f}",
        "-i",
        str(source),
        "-t",
        f"{end_seconds - start_seconds:.3f}",
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-b:a",
        "64k",
        str(output),
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)


def extract_keyframes(
    source: Path,
    output_dir: Path,
    start_seconds: float,
    end_seconds: float,
    count: int = 4,
) -> list[Path]:
    if end_seconds <= start_seconds:
        raise ValueError("end time must be greater than start time")
    output_dir.mkdir(parents=True, exist_ok=True)
    duration = end_seconds - start_seconds
    if count <= 1:
        timestamps = [start_seconds + duration / 2]
    else:
        timestamps = [
            start_seconds + duration * (index + 1) / (count + 1)
            for index in range(count)
        ]
    frames = []
    for index, timestamp in enumerate(timestamps, start=1):
        output = output_dir / f"frame_{index:02d}.jpg"
        command = [
            "ffmpeg",
            "-y",
            "-ss",
            f"{timestamp:.3f}",
            "-i",
            str(source),
            "-frames:v",
            "1",
            "-q:v",
            "3",
            str(output),
        ]
        subprocess.run(command, check=True, capture_output=True, text=True)
        frames.append(output)
    return frames


def suggest_audio_peak_clips(
    source: Path,
    duration: float,
    max_clips: int = 3,
    clip_seconds: float = 32.0,
    analysis_window: float = 8.0,
    step_seconds: float = 6.0,
) -> list[dict]:
    if duration <= 0:
        return []
    if duration <= clip_seconds:
        return [
            {
                "start": 0.0,
                "end": duration,
                "score": 0.5,
                "reason": "auto: 视频较短，整段作为候选高光",
            }
        ]

    windows = []
    cursor = 0.0
    while cursor < max(0.1, duration - analysis_window):
        score = _audio_energy_score(source, cursor, analysis_window)
        if score is not None:
            windows.append({"start": cursor, "score": score})
        cursor += step_seconds

    if not windows:
        return _fallback_clips(duration, max_clips, clip_seconds)

    windows.sort(key=lambda item: item["score"], reverse=True)
    selected: list[dict] = []
    for window in windows:
        center = window["start"] + analysis_window / 2
        start = max(0.0, center - clip_seconds * 0.42)
        end = min(duration, start + clip_seconds)
        start = max(0.0, end - clip_seconds)
        if any(_overlap_ratio(start, end, item["start"], item["end"]) > 0.35 for item in selected):
            continue
        selected.append(
            {
                "start": round(start, 3),
                "end": round(end, 3),
                "score": round(window["score"], 3),
                "reason": "auto: 音频能量峰值候选，适合后续用模型复评剧情连贯性",
            }
        )
        if len(selected) >= max_clips:
            break

    return selected or _fallback_clips(duration, max_clips, clip_seconds)


def _parse_fps(value: Optional[str]) -> float:
    if not value or value == "0/0":
        return 0.0
    if "/" in value:
        numerator, denominator = value.split("/", 1)
        den = float(denominator)
        return float(numerator) / den if den else 0.0
    return float(value)


def _audio_energy_score(source: Path, start_seconds: float, duration: float) -> Optional[float]:
    command = [
        "ffmpeg",
        "-hide_banner",
        "-nostats",
        "-ss",
        f"{start_seconds:.3f}",
        "-t",
        f"{duration:.3f}",
        "-i",
        str(source),
        "-vn",
        "-af",
        "volumedetect",
        "-f",
        "null",
        "-",
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    text = result.stderr
    mean = _extract_db(text, "mean_volume")
    peak = _extract_db(text, "max_volume")
    if mean is None and peak is None:
        return None
    mean_score = 70 + (mean or -70)
    peak_score = 70 + (peak or -70)
    return max(0.0, mean_score * 0.35 + peak_score * 0.65)


def _extract_db(text: str, key: str) -> Optional[float]:
    match = re.search(rf"{key}:\s*(-?\d+(?:\.\d+)?) dB", text)
    return float(match.group(1)) if match else None


def _double_bitrate(value: str) -> str:
    match = re.fullmatch(r"(\d+)([kKmM]?)", value.strip())
    if not match:
        return value
    amount = int(match.group(1)) * 2
    suffix = match.group(2)
    return f"{amount}{suffix}"


def _overlap_ratio(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    overlap = max(0.0, min(a_end, b_end) - max(a_start, b_start))
    shortest = max(0.001, min(a_end - a_start, b_end - b_start))
    return overlap / shortest


def _fallback_clips(duration: float, max_clips: int, clip_seconds: float) -> list[dict]:
    anchors = [0.25, 0.5, 0.75]
    clips = []
    for anchor in anchors[:max_clips]:
        center = duration * anchor
        start = max(0.0, center - clip_seconds / 2)
        end = min(duration, start + clip_seconds)
        start = max(0.0, end - clip_seconds)
        clips.append(
            {
                "start": round(start, 3),
                "end": round(end, 3),
                "score": 0.3,
                "reason": "auto: 未检测到音频峰值，按时间位置生成候选",
            }
        )
    return clips
