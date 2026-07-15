import json
from pathlib import Path
from typing import Optional

from .ai_clients import (
    gemini_review_promo_edit,
    gemini_review_frames,
    generate_voiceover_wav,
    openai_classify_promo_segment,
    openai_draft_promo_edit,
    openai_finalize_promo_edit,
    transcribe_audio,
)
from .config import get_settings
from .ffmpeg import (
    concat_video_segments,
    extract_audio_segment,
    extract_keyframes,
    format_time,
    render_clip_segment,
    render_masked_text_card,
    render_text_card,
)
from .prompts import get_prompt_text


PROMO_ROLES = ["hook", "setup", "relationship", "conflict", "reveal", "emotional_peak", "cliffhanger"]
TARGET_PROMO_SECONDS = 90.0
MAX_PROMO_SECONDS = 112.0
PROMO_WINDOW_SECONDS = 22.0
LEAD_IN_SECONDS = 4.0
REACTION_SECONDS = 4.0
MERGE_GAP_SECONDS = 0.6
OPENING_CARD_SECONDS = 1.2
ENDING_CARD_SECONDS = 3.2
ENDING_CTA_TEXT = "点击下方观看全集"
ENDING_VOICEOVER_TEXT = "想知道她最后怎么反击？点击下方观看全集。"
MAX_PROMO_SCENES = 4
PROMO_VARIANTS = {
    "final": {
        "label": "AI 最终版",
        "roles": ["setup", "relationship", "conflict", "reveal", "cliffhanger"],
        "fallback_title": "这段关系，没那么简单",
        "fallback_ending": "真正的冲突才刚开始",
    },
    "hook": {
        "label": "强钩子版",
        "roles": ["hook", "conflict", "reveal", "emotional_peak", "cliffhanger"],
        "fallback_title": "她一句话，让所有人都愣住了",
        "fallback_ending": "真正的冲突才刚开始",
    },
    "relationship": {
        "label": "关系介绍版",
        "roles": ["setup", "relationship", "conflict", "reveal", "cliffhanger"],
        "fallback_title": "他们的关系，没那么简单",
        "fallback_ending": "这段关系背后还有秘密",
    },
    "reversal": {
        "label": "反转版",
        "roles": ["hook", "setup", "reveal", "conflict", "emotional_peak", "cliffhanger"],
        "fallback_title": "所有人都看错了她",
        "fallback_ending": "下一秒，真相反转",
    },
    "cliffhanger": {
        "label": "悬念版",
        "roles": ["setup", "conflict", "emotional_peak", "reveal", "cliffhanger"],
        "fallback_title": "她最后的选择，改变了一切",
        "fallback_ending": "她到底会怎么选？",
    },
}


def generate_promo_video(
    videos: list[dict],
    limit: int = 3,
    windows_per_video: int = 2,
    variant_mode: str = "single",
    include_cards: bool = True,
) -> dict:
    settings = get_settings()
    settings.promo_dir.mkdir(parents=True, exist_ok=True)
    candidates = []
    for video_index, video in enumerate(videos[:limit]):
        candidates.extend(_analyze_video_for_promo(video, video_index, windows_per_video))
    candidates = _prepare_candidates_for_review(candidates)

    edit_review = _ai_edit_review(candidates)
    selected = _selected_from_review(edit_review, candidates)
    if not selected:
        selected = _extend_for_duration(_select_promo_structure(candidates, PROMO_VARIANTS["relationship"]["roles"]), candidates)

    if not selected:
        return {
            "status": "failed",
            "error": "no usable promo candidates",
            "candidate_count": len(candidates),
            "candidates": candidates,
            "edit_review": edit_review,
        }
    final_variant = _render_variant(
        "final",
        {
            "label": "AI 最终版",
            "roles": [],
            "fallback_title": edit_review.get("opening_text") or "这段关系，没那么简单",
            "fallback_ending": edit_review.get("ending_text") or "真正的冲突才刚开始",
        },
        selected,
        candidates,
        edit_review=edit_review,
        include_cards=include_cards,
    )
    latest = settings.promo_dir / "promo_latest.mp4"
    first_output = Path(final_variant["output_path"])
    latest.write_bytes(first_output.read_bytes())
    variants = [final_variant]
    if variant_mode == "all":
        for variant_key, spec in PROMO_VARIANTS.items():
            if variant_key == "final":
                continue
            variant_selected = _extend_for_duration(_select_promo_structure(candidates, spec["roles"]), candidates)
            if not variant_selected:
                continue
            variants.append(_render_variant(variant_key, spec, variant_selected, candidates, edit_review=edit_review, include_cards=include_cards))
    report = {
        "status": "exported",
        "output_path": str(latest),
        "download_url": "/api/promos/latest/download",
        "structure": final_variant["structure"],
        "opening": final_variant["opening"],
        "ending": final_variant["ending"],
        "variants": variants,
        "candidate_count": len(candidates),
        "analysis_budget": {
            "video_limit": limit,
            "windows_per_video": windows_per_video,
        },
        "candidates": candidates,
        "edit_review": edit_review,
        "title": final_variant["title"],
    }
    report_path = settings.reports_dir / "promo_latest_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _analyze_video_for_promo(video: dict, video_index: int, windows_per_video: int) -> list[dict]:
    duration = float(video.get("duration") or 0)
    if duration <= 0:
        return []
    windows = _promo_windows(duration, windows_per_video)
    source = Path(video["path"])
    settings = get_settings()
    results = []
    for window_index, (start, end) in enumerate(windows):
        label = f"promo_{source.stem}_{format_time(start)}_{format_time(end)}"
        audio_path = settings.work_dir / "audio" / f"{label}.mp3"
        frames_dir = settings.work_dir / "frames" / label
        transcript_result = _safe_audio(source, audio_path, start, end)
        transcript = transcript_result.get("text", "")
        frames = _safe_frames(source, frames_dir, start, end)
        visual = gemini_review_frames(frames, transcript, start, end)
        classification = openai_classify_promo_segment(
            transcript=transcript,
            visual_summary=visual.get("summary", ""),
            start_seconds=start,
            end_seconds=end,
        )
        role = classification.get("role", "skip")
        score = _score(classification.get("promo_score", classification.get("score", 0)))
        if not classification.get("ok", True):
            role = "skip"
        results.append(
            {
                "video": video,
                "start": start,
                "end": end,
                "sequence": video_index * 1000 + window_index,
                "role": role if role in PROMO_ROLES else "skip",
                "score": score,
                "transcript": transcript_result,
                "visual": visual,
                "classification": classification,
            }
        )
    return results


def _promo_windows(duration: float, max_windows: int = 2) -> list[tuple[float, float]]:
    if duration <= PROMO_WINDOW_SECONDS:
        return [(0.0, duration)]
    if max_windows <= 1:
        points = [0.18]
    elif max_windows == 2:
        points = [0.12, 0.78]
    elif max_windows == 3:
        points = [0.08, 0.42, 0.82]
    else:
        points = [0.05, 0.28, 0.55, 0.82]
    windows = []
    for point in points[:max_windows]:
        center = duration * point
        start = max(0.0, center - PROMO_WINDOW_SECONDS / 2)
        end = min(duration, start + PROMO_WINDOW_SECONDS)
        start = max(0.0, end - PROMO_WINDOW_SECONDS)
        windows.append((round(start, 3), round(end, 3)))
    return windows


def _render_variant(
    variant_key: str,
    spec: dict,
    selected: list[dict],
    candidates: list[dict],
    edit_review: Optional[dict] = None,
    include_cards: bool = True,
) -> dict:
    settings = get_settings()
    selected = _normalize_timeline(selected)
    title = (edit_review or {}).get("opening_text") or _best_title(selected, spec["fallback_title"])
    ending_text = (edit_review or {}).get("ending_text") or _ending_text(selected, spec["fallback_ending"])
    ending_voiceover = {}
    rendered_segments = []
    if include_cards:
        opening_card = settings.work_dir / "clips" / f"promo_{variant_key}_00_opening_card.mp4"
        ending_card = settings.work_dir / "clips" / f"promo_{variant_key}_99_ending_card.mp4"
        opening_source = _card_source(selected, prefer_last=False)
        ending_source = _card_source(selected, prefer_last=True)
        ending_voiceover = _generate_ending_voiceover(variant_key)
        _render_card(opening_card, opening_source, title, _opening_subtitle(selected), duration_seconds=OPENING_CARD_SECONDS)
        _render_card(
            ending_card,
            ending_source,
            ending_text,
            ENDING_CTA_TEXT,
            duration_seconds=ENDING_CARD_SECONDS,
            vertical_shift=-130,
            audio_path=Path(ending_voiceover["output_path"]) if ending_voiceover.get("ok") else None,
        )
        rendered_segments.append(opening_card)
    for index, item in enumerate(selected, start=1):
        source = Path(item["video"]["path"])
        start, end = _expanded_range(item)
        segment = settings.work_dir / "clips" / (
            f"promo_{variant_key}_{index:02d}_{source.stem}_{format_time(start)}_{format_time(end)}.mp4"
        )
        render_clip_segment(source, segment, start, end)
        rendered_segments.append(segment)
    if include_cards:
        rendered_segments.append(ending_card)

    output = settings.promo_dir / f"promo_{variant_key}.mp4"
    concat_video_segments(rendered_segments, output)
    return {
        "key": variant_key,
        "label": spec["label"],
        "status": "exported",
        "output_path": str(output),
        "download_url": f"/api/promos/{variant_key}/download",
        "title": title,
        "opening": {
            "title": title,
            "subtitle": _opening_subtitle(selected),
        },
        "ending": {
            "title": ending_text,
            "subtitle": ENDING_CTA_TEXT,
            "voiceover": ending_voiceover,
        },
        "scores": _variant_scores(selected),
        "structure": _structure_with_cut_ranges(selected),
        "candidate_count": len(candidates),
        "duration_target_seconds": TARGET_PROMO_SECONDS,
        "duration_estimate_seconds": round(_total_duration(selected) + (OPENING_CARD_SECONDS + ENDING_CARD_SECONDS if include_cards else 0), 3),
        "internal_cards_enabled": include_cards,
        "edit_review": edit_review or {},
    }


def _expanded_range(item: dict) -> tuple[float, float]:
    duration = float((item.get("video") or {}).get("duration") or 0)
    start = max(0.0, float(item["start"]) - LEAD_IN_SECONDS)
    end = float(item["end"]) + REACTION_SECONDS
    if duration > 0:
        end = min(duration, end)
    if end <= start:
        end = float(item["end"])
    return round(start, 3), round(end, 3)


def _normalize_timeline(items: list[dict]) -> list[dict]:
    ordered = sorted(items, key=lambda item: (item.get("sequence", 0), item["video"]["path"], item["start"]))
    merged: list[dict] = []
    for item in ordered:
        if not merged:
            merged.append(dict(item))
            continue
        previous = merged[-1]
        same_video = previous["video"]["path"] == item["video"]["path"]
        previous_start, previous_end = _expanded_range(previous)
        item_start, _ = _expanded_range(item)
        close_enough = item_start <= previous_end + MERGE_GAP_SECONDS
        if same_video and close_enough:
            previous["end"] = max(previous["end"], item["end"])
            previous["score"] = max(previous.get("score", 0), item.get("score", 0))
            previous["role"] = previous.get("role") or item.get("role")
            continue
        merged.append(dict(item))
    return merged


def _render_card(
    output: Path,
    item: Optional[dict],
    title: str,
    subtitle: str,
    duration_seconds: float,
    vertical_shift: int = 0,
    audio_path: Optional[Path] = None,
) -> None:
    if item:
        render_masked_text_card(
            output,
            Path(item["video"]["path"]),
            item["start"],
            title,
            subtitle,
            duration_seconds=duration_seconds,
            vertical_shift=vertical_shift,
            audio_path=audio_path,
        )
        return
    render_text_card(output, title, subtitle, duration_seconds=duration_seconds, vertical_shift=vertical_shift, audio_path=audio_path)


def _generate_ending_voiceover(variant_key: str) -> dict:
    settings = get_settings()
    output = settings.work_dir / "audio" / f"promo_{variant_key}_ending_voiceover.wav"
    return generate_voiceover_wav(
        ENDING_VOICEOVER_TEXT,
        output,
        style=get_prompt_text("ending_voiceover_style"),
    )


def _card_source(selected: list[dict], prefer_last: bool) -> Optional[dict]:
    if not selected:
        return None
    ordered = list(reversed(selected)) if prefer_last else selected
    return ordered[0]


def _select_promo_structure(candidates: list[dict], roles: Optional[list[str]] = None) -> list[dict]:
    selected = []
    roles = roles or ["hook", "setup", "relationship", "conflict", "reveal", "emotional_peak", "cliffhanger"]
    hook = _best_for_role(candidates, "hook", selected)
    if hook and "hook" in roles:
        selected.append(hook)

    min_sequence = None
    for role in [role for role in roles if role != "hook"]:
        match = _best_for_role(candidates, role, selected, min_sequence=min_sequence)
        if match:
            selected.append(match)
            if role in {"setup", "relationship", "conflict", "reveal", "emotional_peak"}:
                min_sequence = match.get("sequence", min_sequence)
    if len(selected) < 3:
        fallback = sorted(
            [item for item in candidates if item.get("role") != "skip" and item not in selected],
            key=lambda item: item.get("score", 0),
            reverse=True,
        )
        selected.extend(fallback[: MAX_PROMO_SCENES - len(selected)])
    return selected[:MAX_PROMO_SCENES]


def _extend_for_duration(selected: list[dict], candidates: list[dict]) -> list[dict]:
    result = list(selected)
    used = {_candidate_key(item) for item in result}
    preferred = sorted(
        [item for item in candidates if item.get("role") != "skip" and _candidate_key(item) not in used],
        key=lambda item: (item.get("sequence", 0), -item.get("score", 0)),
    )
    context = sorted(
        [item for item in candidates if item.get("role") == "skip" and _candidate_key(item) not in used],
        key=lambda item: (item.get("sequence", 0), -item.get("score", 0)),
    )
    fallback = preferred + context
    for item in fallback:
        current = _total_duration(result) + OPENING_CARD_SECONDS + ENDING_CARD_SECONDS
        candidate_start, candidate_end = _expanded_range(item)
        candidate_duration = candidate_end - candidate_start
        if current >= TARGET_PROMO_SECONDS:
            break
        if len(_normalize_timeline(result)) >= MAX_PROMO_SCENES:
            break
        if current + candidate_duration > MAX_PROMO_SECONDS:
            continue
        result.append(item)
        used.add(_candidate_key(item))
    result.sort(key=lambda item: item.get("sequence", 0))
    return result


def _prepare_candidates_for_review(candidates: list[dict]) -> list[dict]:
    prepared = []
    for index, item in enumerate(candidates, start=1):
        enriched = dict(item)
        cut_start, cut_end = _expanded_range(enriched)
        enriched["candidate_id"] = index
        enriched["cut_start"] = cut_start
        enriched["cut_end"] = cut_end
        enriched["cut_duration"] = round(max(0.0, cut_end - cut_start), 3)
        prepared.append(enriched)
    return prepared


def _ai_edit_review(candidates: list[dict]) -> dict:
    if not candidates:
        return {"ok": False, "mode": "fallback", "error": "no candidates"}
    draft = openai_draft_promo_edit(candidates, TARGET_PROMO_SECONDS)
    gemini_review = gemini_review_promo_edit(candidates, draft, TARGET_PROMO_SECONDS)
    final = openai_finalize_promo_edit(candidates, draft, gemini_review, TARGET_PROMO_SECONDS)
    selected_ids = _candidate_ids(final.get("selected_candidate_ids"))
    if not selected_ids:
        selected_ids = _candidate_ids(gemini_review.get("suggested_candidate_ids"))
    if not selected_ids:
        selected_ids = _candidate_ids(draft.get("selected_candidate_ids"))
    ok = bool(selected_ids)
    return {
        "ok": ok,
        "mode": "gpt_gemini_final" if ok and final.get("ok") else "fallback",
        "selected_candidate_ids": selected_ids,
        "opening_text": final.get("opening_text") or gemini_review.get("opening_text") or draft.get("opening_text"),
        "ending_text": final.get("ending_text") or gemini_review.get("ending_text") or draft.get("ending_text"),
        "storyline": final.get("storyline") or draft.get("storyline"),
        "continuity_notes": final.get("continuity_notes") or draft.get("continuity_notes"),
        "decision_reason": final.get("decision_reason") or gemini_review.get("reason"),
        "gpt_draft": draft,
        "gemini_review": gemini_review,
        "gpt_final": final,
    }


def _selected_from_review(edit_review: dict, candidates: list[dict]) -> list[dict]:
    by_id = {int(item["candidate_id"]): item for item in candidates if item.get("candidate_id") is not None}
    selected = []
    for candidate_id in _candidate_ids(edit_review.get("selected_candidate_ids")):
        item = by_id.get(candidate_id)
        if item and item not in selected:
            selected.append(item)
    selected = _normalize_timeline(selected)
    if selected and _total_duration(selected) + OPENING_CARD_SECONDS + ENDING_CARD_SECONDS < TARGET_PROMO_SECONDS:
        selected = _extend_for_duration(selected, candidates)
    return selected[:MAX_PROMO_SCENES]


def _candidate_ids(value) -> list[int]:
    if not isinstance(value, list):
        return []
    ids = []
    for item in value:
        try:
            ids.append(int(item))
        except (TypeError, ValueError):
            continue
    return ids


def _structure_with_cut_ranges(items: list[dict]) -> list[dict]:
    structure = []
    for item in items:
        enriched = dict(item)
        cut_start, cut_end = _expanded_range(item)
        enriched["analysis_start"] = item["start"]
        enriched["analysis_end"] = item["end"]
        enriched["cut_start"] = cut_start
        enriched["cut_end"] = cut_end
        enriched["cut_duration"] = round(max(0.0, cut_end - cut_start), 3)
        structure.append(enriched)
    return structure


def _total_duration(items: list[dict]) -> float:
    total = 0.0
    for item in _normalize_timeline(items):
        start, end = _expanded_range(item)
        total += max(0.0, end - start)
    return total


def _candidate_key(item: dict) -> tuple:
    return (item["video"]["path"], item["start"], item["end"])


def _best_for_role(
    candidates: list[dict],
    role: str,
    selected: list[dict],
    min_sequence: Optional[float] = None,
) -> Optional[dict]:
    used = {(item["video"]["path"], item["start"], item["end"]) for item in selected}
    matches = [
        item
        for item in candidates
        if item.get("role") == role
        and (item["video"]["path"], item["start"], item["end"]) not in used
        and (min_sequence is None or item.get("sequence", 0) >= min_sequence)
    ]
    if not matches and min_sequence is not None:
        return _best_for_role(candidates, role, selected, min_sequence=None)
    matches.sort(key=lambda item: item.get("score", 0), reverse=True)
    return matches[0] if matches else None


def _safe_audio(source: Path, audio_path: Path, start: float, end: float) -> dict:
    try:
        extract_audio_segment(source, audio_path, start, end)
        return transcribe_audio(audio_path)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "text": "", "error": str(exc)}


def _safe_frames(source: Path, frames_dir: Path, start: float, end: float) -> list[Path]:
    try:
        return extract_keyframes(source, frames_dir, start, end, count=3)
    except Exception:
        return []


def _score(value) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _variant_scores(selected: list[dict]) -> dict:
    if not selected:
        return {"opening_strength": 0.0, "cliffhanger_strength": 0.0, "avg_promo_score": 0.0}
    opening = max(
        (_score((item.get("classification") or {}).get("opening_strength")) for item in selected),
        default=0.0,
    )
    cliffhanger = max(
        (_score((item.get("classification") or {}).get("cliffhanger_strength")) for item in selected),
        default=0.0,
    )
    avg = sum(item.get("score", 0.0) for item in selected) / len(selected)
    return {
        "opening_strength": round(opening, 3),
        "cliffhanger_strength": round(cliffhanger, 3),
        "avg_promo_score": round(avg, 3),
    }


def _best_title(selected: list[dict], fallback: str = "她以为只是开始，真相却藏在下一集") -> str:
    for item in selected:
        classification = item.get("classification") or {}
        title = classification.get("opening_text") or classification.get("title_hook")
        if title:
            return title
    return fallback


def _opening_subtitle(selected: list[dict]) -> str:
    for item in selected:
        classification = item.get("classification") or {}
        if classification.get("voiceover"):
            return classification["voiceover"]
    return "一段关系，藏着一个不能说的真相"


def _ending_text(selected: list[dict], fallback: str = "真相揭开前，她做了一个决定") -> str:
    for item in reversed(selected):
        classification = item.get("classification") or {}
        text = classification.get("ending_text")
        if text:
            return text
        if item.get("role") == "cliffhanger" and classification.get("title_hook"):
            return classification["title_hook"]
    return fallback
