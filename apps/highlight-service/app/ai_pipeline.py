import json
from pathlib import Path

from .ai_clients import (
    gemini_review_frames,
    openai_analyze_transcript,
    transcribe_audio,
)
from .config import get_settings
from .ffmpeg import extract_audio_segment, extract_keyframes, format_time


def enrich_suggestions_with_ai(
    video: dict,
    suggestions: list[dict],
) -> tuple[list[dict], dict]:
    settings = get_settings()
    source = Path(video["path"])
    run_id = source.stem.replace(" ", "_")
    enriched = []
    for index, suggestion in enumerate(suggestions, start=1):
        start = float(suggestion["start"])
        end = float(suggestion["end"])
        label = f"{run_id}_{format_time(start)}_{format_time(end)}"
        audio_path = settings.work_dir / "audio" / f"{label}.mp3"
        frames_dir = settings.work_dir / "frames" / label

        transcript_result = _safe_transcribe(source, audio_path, start, end)
        transcript = transcript_result.get("text", "")
        text_review = openai_analyze_transcript(transcript, start, end)
        frame_paths = _safe_keyframes(source, frames_dir, start, end)
        visual_review = gemini_review_frames(frame_paths, transcript, start, end)

        score = _combined_score(
            float(suggestion.get("score") or 0.0),
            _score(text_review),
            _score(visual_review),
        )
        reason = _build_reason(suggestion, transcript_result, text_review, visual_review)
        enriched.append(
            {
                **suggestion,
                "score": score,
                "reason": reason,
                "ai": {
                    "transcript": transcript_result,
                    "text_review": text_review,
                    "visual_review": visual_review,
                    "frame_paths": [str(path) for path in frame_paths],
                },
                "rank": index,
            }
        )

    model_review = {
        "provider": "gpt_gemini",
        "decision": "reviewed",
        "reason": "候选片段已完成转写、台词分析和画面复评。",
    }
    _write_report(video, enriched, model_review)
    return enriched, model_review


def _safe_transcribe(source: Path, audio_path: Path, start: float, end: float) -> dict:
    try:
        extract_audio_segment(source, audio_path, start, end)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "text": "", "error": f"audio extraction failed: {exc}"}
    return transcribe_audio(audio_path)


def _safe_keyframes(source: Path, frames_dir: Path, start: float, end: float) -> list[Path]:
    try:
        return extract_keyframes(source, frames_dir, start, end)
    except Exception:
        return []


def _score(result: dict) -> float:
    try:
        return max(0.0, min(1.0, float(result.get("score") or 0.0)))
    except (TypeError, ValueError):
        return 0.0


def _combined_score(local_score: float, text_score: float, visual_score: float) -> float:
    local_normalized = max(0.0, min(1.0, local_score / 100.0))
    return round(local_normalized * 0.25 + text_score * 0.35 + visual_score * 0.40, 3)


def _build_reason(
    suggestion: dict,
    transcript_result: dict,
    text_review: dict,
    visual_review: dict,
) -> str:
    parts = [suggestion.get("reason", "auto candidate")]
    if transcript_result.get("ok"):
        parts.append("OpenAI 已转写")
    else:
        parts.append(f"OpenAI 转写失败: {transcript_result.get('error', 'unknown')}")
    if text_review.get("ok"):
        parts.append(f"台词: {text_review.get('summary', '')}".strip())
    elif text_review.get("error"):
        parts.append(f"台词分析失败: {text_review.get('error')}")
    if visual_review.get("ok"):
        parts.append(f"画面: {visual_review.get('summary', '')}".strip())
    elif visual_review.get("error"):
        parts.append(f"Gemini 复评失败: {visual_review.get('error')}")
    return " | ".join(part for part in parts if part)


def _write_report(video: dict, enriched: list[dict], model_review: dict) -> None:
    settings = get_settings()
    settings.reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = settings.reports_dir / f"{Path(video['path']).stem}_ai_report.json"
    report_path.write_text(
        json.dumps(
            {
                "video": video,
                "clips": enriched,
                "model_review": model_review,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
