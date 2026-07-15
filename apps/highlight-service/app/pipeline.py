from __future__ import annotations

import json
import re
import socket
from pathlib import Path
from typing import Callable

from fastapi import HTTPException

from .ai_pipeline import enrich_suggestions_with_ai
from .ai_clients import gemini_watch_story_quality_proxies, generate_short_drama_template_visual
from .config import get_settings
from .db import connect, rows_to_dicts
from .ffmpeg import (
    concat_video_segments,
    cut_clip,
    extract_keyframes,
    extract_frame_image,
    format_time,
    probe_video,
    render_clip_segment,
    render_image_segment,
    render_text_card,
    render_proxy_video,
    suggest_audio_peak_clips,
)
from .models import PipelineRunCreate
from .projects import record_generated_asset
from .promo_pipeline import generate_promo_video


DEFAULT_PUBLISH_TAGS = ["#快来看短剧", "#AI创想家计划", "#神仙剪刀手"]
STALE_PIPELINE_JOB_MINUTES = 30
REVIEW_COVER_DURATION_SECONDS = 1.5
OUTRO_CTA_DURATION_SECONDS = 3.0


class ReviewPackImageError(RuntimeError):
    pass


def _normalize_publish_tag(value: str) -> str:
    tag = value.strip()
    if not tag:
        return ""
    tag = tag.lstrip("#").strip()
    if not tag:
        return ""
    return f"#{tag}"


def _publish_tags(asset_type: str, *, pipeline: str = "") -> list[str]:
    tags = [*DEFAULT_PUBLISH_TAGS, "#短剧", "#追剧"]
    if pipeline == "story_quality_cut" or asset_type == "quality_cut":
        tags.extend(["#剧情精剪", "#高能剧情"])
    elif pipeline == "story_promo_mix":
        tags.extend(["#短剧推荐", "#高能混剪"])
    elif asset_type == "promo":
        tags.extend(["#短剧推荐", "#高能反转"])
    elif asset_type == "highlight":
        tags.extend(["#高能片段", "#名场面"])
    normalized = []
    for tag in tags:
        formatted = _normalize_publish_tag(tag)
        if formatted and formatted not in normalized:
            normalized.append(formatted)
    return normalized


INTERNAL_REVIEW_TITLES = {"剧情精剪", "剧情引流总剪", "引流视频", "引流多版本"}


def _safe_viewer_title(title: str) -> str:
    clean_title = title.strip()
    if not clean_title or clean_title in INTERNAL_REVIEW_TITLES:
        return "短剧高能片段"
    return clean_title


STORY_SIGNAL_WORDS = (
    "身份",
    "真相",
    "反转",
    "误会",
    "旧账",
    "秘密",
    "危机",
    "威胁",
    "复仇",
    "背叛",
    "遗嘱",
    "继承",
    "家产",
    "婚姻",
    "离婚",
    "求婚",
    "逼婚",
    "千金",
    "总裁",
    "保安",
    "保镖",
    "女神",
    "豪门",
    "亲情",
    "母亲",
    "父亲",
    "女儿",
    "儿子",
    "夫妻",
    "女主",
    "男主",
    "上海滩",
    "风云",
)

EDITING_MARKERS = (
    "MVP",
    "低清代理",
    "keep/drop",
    "下一步接入",
    "剪辑",
    "保留",
    "删除",
    "低效",
    "镜头",
    "节奏",
    "叙事",
    "连贯",
    "审片",
    "模型",
    "片段",
    "输出",
    "生成",
    "核心",
    "建立",
    "展现",
    "强调",
    "推进",
    "铺垫",
    "烘托",
    "强化",
)


def _promo_copy(title: str, asset_type: str, *, storyline: str = "", pipeline: str = "", quality_notes: str = "") -> dict:
    clean_title = _safe_viewer_title(title)
    clean_storyline = storyline.strip()
    if pipeline == "story_quality_cut" or asset_type == "quality_cut":
        hook = _viewer_hook_from_text(clean_storyline)
        copy = hook or _quality_cut_fallback_copy(clean_title)
    elif pipeline == "story_promo_mix":
        hook = clean_storyline or "前一秒还在试探，下一秒局面彻底失控"
        copy = f"{hook}。关系越拉越紧，反转一个接一个，看到最后才发现真正的狠角色还没出手。"
    elif asset_type == "promo":
        hook = clean_storyline or "本以为只是一次普通相遇，没想到从这里开始全员命运都被改写"
        copy = f"{hook}。身份、误会和旧账一起爆开，每一个眼神都像在埋下一次反转。"
    elif asset_type == "highlight":
        copy = f"《{clean_title}》这一幕太上头了，话刚说出口，局势就彻底变了。错过前面还能补，错过这里真的亏。"
    else:
        copy = f"《{clean_title}》刚开始还以为能猜到结局，结果越往后越不对劲，真正的反转才刚刚开始。"
    return {"promo_copy_title": "宣传文案", "promo_copy": copy, "publish_tags": _publish_tags(asset_type, pipeline=pipeline)}


def _quality_cut_fallback_copy(clean_title: str) -> str:
    if clean_title and clean_title != "短剧高能片段":
        if any(word in clean_title for word in ("遗嘱", "继承", "家产")):
            return f"《{clean_title}》一份遗嘱把亲情、旧账和利益全摆上台面，谁是真心谁在算计，很快就藏不住了。"
        if any(word in clean_title for word in ("婚姻", "离婚", "妻", "夫", "千金")):
            return f"《{clean_title}》婚姻里的委屈刚被撕开，隐藏身份和旧账就一起翻涌上来，越到后面越想看她怎么反击。"
        if any(word in clean_title for word in ("上海滩", "风云", "江湖")):
            return f"《{clean_title}》乱局里各方势力步步紧逼，旧恩怨和新危机接连爆开，真正的较量才刚开始。"
        if any(word in clean_title for word in ("保安", "保镖", "总裁", "女神", "求婚")):
            return f"《{clean_title}》身份差距和意外求婚把局面瞬间点燃，旁人的轻视越重，后面的反转越狠。"
        return f"《{clean_title}》人物关系刚被撕开，新的危机就追了上来。每一段对话都在把真相推向失控边缘。"
    return "人物关系刚被撕开，新的危机就追了上来。每一段对话都在把真相推向失控边缘。"


def _story_candidate_sentences(text: str) -> list[tuple[int, str]]:
    clean = " ".join((text or "").replace("\r", "\n").split())
    if not clean:
        return []
    candidates: list[tuple[int, str]] = []
    for item in re.split(r"[。！？!?；;\n|]+", clean):
        sentence = item.strip(" 。；;，,")
        if len(sentence) < 8:
            continue
        sentence = re.sub(r"^(优先|主要|建议|可|应)?保留(所有|能|了|出|住|其|这段|该段)?", "", sentence).strip(" ，,")
        if len(sentence) < 8:
            continue
        if len(sentence) > 54:
            sentence = sentence[:54].rstrip("，,；;")
        story_score = sum(1 for word in STORY_SIGNAL_WORDS if word in sentence)
        editing_score = sum(1 for word in EDITING_MARKERS if word in sentence)
        if editing_score and story_score == 0:
            continue
        if any(marker in sentence for marker in ("本地候选窗口", "大模型审片", "低清代理视频")):
            continue
        score = story_score * 3 - editing_score
        if score <= 0 and not any(word in sentence for word in ("他", "她", "两人", "众人", "家里", "当众")):
            continue
        candidates.append((score, sentence))
    return candidates


def _viewer_hook_from_text(text: str) -> str:
    candidates = _story_candidate_sentences(text)
    candidates.sort(key=lambda item: (-item[0], len(item[1])))
    for _, sentence in candidates:
        if 12 <= len(sentence) <= 42:
            return sentence + "。"
    if candidates:
        return candidates[0][1][:42].rstrip("，,；;") + "。"
    return ""


def _cover_enabled(context: dict) -> bool:
    return True


def _outro_enabled(context: dict) -> bool:
    return True


def _prepend_review_cover(
    context: dict,
    *,
    title: str,
    subtitle: str,
    pipeline: str,
    rendered_segments: list[Path],
    duration_seconds: float = REVIEW_COVER_DURATION_SECONDS,
) -> tuple[list[Path], dict]:
    if not _cover_enabled(context):
        return rendered_segments, {"enabled": False}
    cover_dir = get_settings().work_dir / "covers" / f"run_{context['run_id']}"
    cover_dir.mkdir(parents=True, exist_ok=True)
    image_path = cover_dir / "review_cover.png"
    segment_path = cover_dir / "review_cover.mp4"
    source_names = "、".join(
        str(video.get("name") or f"素材{index}")
        for index, video in enumerate(context.get("videos") or [], start=1)
    )
    story_context = _review_pack_story_context(context)
    reference_frame = _review_pack_reference_frame(context)
    viewer_title = _safe_viewer_title(title)
    brief = _build_review_cover_poster_brief(
        context,
        title=viewer_title,
        subtitle=subtitle,
        pipeline=pipeline,
        source_names=source_names,
        story_context=story_context,
        duration_seconds=duration_seconds,
    )
    image_result = generate_short_drama_template_visual(
        kind="intro",
        drama_name=viewer_title,
        style="短剧宣传海报、强剧情冲突、电影感竖屏视觉、高点击封面",
        brief=brief,
        duration=int(max(1, round(duration_seconds))),
        output_path=image_path,
        reference_image_path=reference_frame,
    )
    mode = image_result.get("model") or "gpt-image-2"
    fallback_result = None
    error = ""
    if not image_result.get("ok") or not image_path.exists():
        error = image_result.get("error") or "cover image generation failed"
        fallback_result = generate_short_drama_template_visual(
            kind="intro",
            drama_name=viewer_title,
            style="短剧宣传海报、强剧情冲突、电影感竖屏视觉、高点击封面",
            brief=brief,
            duration=int(max(1, round(duration_seconds))),
            output_path=image_path,
            reference_image_path=reference_frame,
            image_model="gpt-image-1.5",
        )
        image_result = fallback_result
        mode = fallback_result.get("model") or "gpt-image-1.5"
    if not image_result.get("ok") or not image_path.exists():
        error = image_result.get("error") or error or "cover image generation failed"
        frame_result = _render_one_second_cover(context, image_path, segment_path, duration_seconds)
        if not frame_result.get("ok"):
            raise ReviewPackImageError(f"封面生成失败，1 秒帧兜底也失败：{frame_result.get('error') or error}")
        mode = "one_second_frame_fallback"
        image_result = {
            "ok": True,
            "fallback_from": "gpt-image-2,gpt-image-1.5",
            "error": error,
            **frame_result,
        }
    else:
        try:
            render_image_segment(image_path, segment_path, duration_seconds=duration_seconds)
        except Exception as exc:  # noqa: BLE001 - cover should not fail the whole export.
            error = str(exc)
            raise ReviewPackImageError(f"GPT Image 2 片头转视频失败：{error}") from exc
    cover_info = {
        "enabled": True,
        "mode": mode,
        "duration": duration_seconds,
        "image_path": str(image_path) if image_path.exists() else "",
        "segment_path": str(segment_path),
        "prompt_brief": brief,
        "reference_frame": str(reference_frame) if reference_frame else "",
        "image_result": image_result,
        "fallback_result": fallback_result,
        "error": error,
    }
    return [segment_path, *rendered_segments], cover_info


def _build_review_cover_poster_brief(
    context: dict,
    *,
    title: str,
    subtitle: str,
    pipeline: str,
    source_names: str,
    story_context: str,
    duration_seconds: float,
) -> str:
    artifacts = context.get("artifacts") or {}
    model_review = artifacts.get("model_watch_quality_cut") or {}
    validated = artifacts.get("validate_quality_edit_decisions") or {}
    kept_segments = _review_pack_kept_segments(context)
    kept_summary = []
    for item in kept_segments[:8]:
        name = str(item.get("source_video_name") or "").strip()
        reason = str(item.get("reason") or item.get("role") or "").strip()
        kept_summary.append(f"{name} {item.get('start')}-{item.get('end')}秒：{reason[:90]}")
    source_summaries = []
    for item in validated.get("source_summaries") or []:
        summary = str(item.get("summary") or item.get("quality_notes") or item.get("title") or item).strip()
        if summary:
            source_summaries.append(summary[:160])
    return (
        f"任务：请让 gpt-image-2 根据视频解析结果，为短剧成片生成一张竖屏宣传海报，并作为{duration_seconds:g}秒首帧封面使用。\n"
        f"管道：{pipeline}\n"
        f"素材：{source_names[:180]}\n"
        f"短剧展示名：{title}\n"
        f"观众侧宣传文案：{subtitle[:260]}\n"
        f"视频解析摘要：{str(model_review.get('summary') or '')[:500]}\n"
        f"质量审片结论：{str(model_review.get('quality_notes') or validated.get('quality_notes') or '')[:500]}\n"
        f"保留剧情片段：{'；'.join(kept_summary)[:900]}\n"
        f"单集/素材理解：{'；'.join(source_summaries)[:500]}\n"
        f"综合剧情理解：{story_context[:900]}\n"
        "海报目标：必须像短剧平台用于吸引点击的宣传海报，而不是普通片头文字卡。"
        "画面要把视频解析出的主要人物关系、核心矛盾、命运转折或悬念可视化；"
        "优先选择一个最能代表剧情冲突的瞬间做主体，不要把多个无关场景拼贴成杂乱拼图。"
        "如果参考帧存在，人物服装、年龄感、场景氛围和短剧质感必须贴近参考帧。"
        "构图为 9:16 竖屏电影海报：强主体、强情绪、高对比、背景有剧情层次，移动端小屏一眼能懂。"
        "文字规则：中文文字越少越好；如需文字，只允许放短剧展示名，不写副标题、营销词、制作说明、流程说明。"
        "安全约束：不要平台 logo、水印、二维码、真实 App UI、血腥低俗内容、廉价渐变背景；不要遮住人物脸部。"
    )


def _render_one_second_cover(context: dict, image_path: Path, segment_path: Path, duration_seconds: float) -> dict:
    videos = context.get("videos") or []
    if not videos and context.get("video"):
        videos = [context["video"]]
    source_path = ""
    try:
        source_path = str((videos[0] or {}).get("path") or "")
        if not source_path:
            return {"ok": False, "error": "no source video for 1-second cover"}
        extract_frame_image(Path(source_path), image_path, 1)
        render_image_segment(image_path, segment_path, duration_seconds=duration_seconds)
        return {
            "ok": True,
            "provider": "local_ffmpeg",
            "mode": "one_second_frame",
            "timestamp": 1,
            "source_path": source_path,
            "image_path": str(image_path),
            "segment_path": str(segment_path),
        }
    except Exception as exc:  # noqa: BLE001 - final fallback should report exact reason.
        return {"ok": False, "error": str(exc), "source_path": source_path}


def _append_full_episode_cta(
    context: dict,
    *,
    title: str,
    pipeline: str,
    rendered_segments: list[Path],
    duration_seconds: float = OUTRO_CTA_DURATION_SECONDS,
) -> tuple[list[Path], dict]:
    if not _outro_enabled(context):
        return rendered_segments, {"enabled": False}
    outro_dir = get_settings().work_dir / "outros" / f"run_{context['run_id']}"
    outro_dir.mkdir(parents=True, exist_ok=True)
    image_path = outro_dir / "full_episode_cta.png"
    segment_path = outro_dir / "full_episode_cta.mp4"
    cta_title = "点击左下角"
    cta_subtitle = "观看全集"
    story_context = _review_pack_story_context(context)
    reference_frame = _review_pack_reference_frame(context)
    viewer_title = _safe_viewer_title(title)
    brief = (
        f"为短剧成片生成片尾引导图。管道={pipeline}。"
        f"短剧/素材展示名={viewer_title}。"
        f"短剧内容理解={story_context[:1200]}。"
        "目标是在视频最后清楚引导用户点击左下角观看全集，同时保留本短剧的剧情悬念和人物情绪。"
        "请基于参考帧和剧情内容生成真实短剧片尾视觉图：有剧情余味、有悬念，不像硬广告落版。"
        "中文文字必须简短准确：点击左下角、观看全集。"
        "构图要给左下角留明显视觉动线，可以用箭头/光效/手势暗示，但不要过度花哨。"
        "不要二维码、水印、平台 logo，不要廉价模板感，不要遮住核心人物脸部。"
    )
    image_result = generate_short_drama_template_visual(
        kind="outro",
        drama_name=viewer_title,
        style="过审友好、短剧片尾引导、清晰点击动线",
        brief=brief,
        duration=int(max(1, round(duration_seconds))),
        output_path=image_path,
        reference_image_path=reference_frame,
    )
    mode = image_result.get("model") or "gpt-image-2"
    fallback_result = None
    error = ""
    if not image_result.get("ok") or not image_path.exists():
        error = image_result.get("error") or "outro image generation failed"
        fallback_result = generate_short_drama_template_visual(
            kind="outro",
            drama_name=viewer_title,
            style="过审友好、短剧片尾引导、清晰点击动线",
            brief=brief,
            duration=int(max(1, round(duration_seconds))),
            output_path=image_path,
            reference_image_path=reference_frame,
            image_model="gpt-image-1.5",
        )
        image_result = fallback_result
        mode = fallback_result.get("model") or "gpt-image-1.5"
    if not image_result.get("ok") or not image_path.exists():
        error = image_result.get("error") or error or "outro image generation failed"
        raise ReviewPackImageError(f"GPT Image 2/1.5 片尾生成失败：{error}")
    else:
        try:
            render_image_segment(image_path, segment_path, duration_seconds=duration_seconds)
        except Exception as exc:  # noqa: BLE001 - outro should not fail the whole export.
            error = str(exc)
            raise ReviewPackImageError(f"GPT Image 2 片尾转视频失败：{error}") from exc
    outro_info = {
        "enabled": True,
        "mode": mode,
        "duration": duration_seconds,
        "title": cta_title,
        "subtitle": cta_subtitle,
        "image_path": str(image_path) if image_path.exists() else "",
        "segment_path": str(segment_path),
        "prompt_brief": brief,
        "reference_frame": str(reference_frame) if reference_frame else "",
        "image_result": image_result,
        "fallback_result": fallback_result,
        "error": error,
    }
    return [*rendered_segments, segment_path], outro_info


def _wrap_existing_output_with_review_pack(
    context: dict,
    *,
    output_path: Path,
    title: str,
    subtitle: str,
    pipeline: str,
    duration_seconds: float = REVIEW_COVER_DURATION_SECONDS,
) -> dict:
    if not output_path.exists():
        return {"enabled": False, "error": "output file not found"}
    temp_dir = get_settings().work_dir / "review-pack" / f"run_{context['run_id']}" / output_path.stem
    temp_dir.mkdir(parents=True, exist_ok=True)
    body_segment = temp_dir / "body.mp4"
    wrapped_output = temp_dir / "with_review_pack.mp4"
    info = probe_video(output_path)
    duration = float(info.get("duration") or 0)
    if duration <= 0:
        return {"enabled": False, "error": "output duration is empty"}
    render_clip_segment(output_path, body_segment, 0, duration)
    cover_segment = context.get("review_cover_segment")
    cover_info = context.get("review_cover_info")
    if cover_segment and Path(cover_segment).exists():
        cover_info = cover_info or {"enabled": True, "mode": "pre_generated", "duration": duration_seconds, "segment_path": str(cover_segment)}
        segments = [Path(cover_segment), body_segment]
    else:
        segments, cover_info = _prepend_review_cover(
            context,
            title=title,
            subtitle=subtitle,
            pipeline=pipeline,
            rendered_segments=[body_segment],
            duration_seconds=duration_seconds,
        )
    outro_segment = context.get("outro_cta_segment")
    outro_info = context.get("outro_cta_info")
    if outro_segment and Path(outro_segment).exists():
        outro_info = outro_info or {"enabled": True, "mode": "pre_generated", "duration": OUTRO_CTA_DURATION_SECONDS, "segment_path": str(outro_segment)}
        segments = [*segments, Path(outro_segment)]
    else:
        segments, outro_info = _append_full_episode_cta(
            context,
            title=title,
            pipeline=pipeline,
            rendered_segments=segments,
        )
    if not cover_info.get("enabled") and not outro_info.get("enabled"):
        return {"enabled": False, "review_cover": cover_info, "outro_cta": outro_info}
    concat_video_segments(segments, wrapped_output)
    wrapped_output.replace(output_path)
    return {
        "enabled": True,
        "review_cover": cover_info,
        "outro_cta": outro_info,
        "wrapped_output_path": str(output_path),
        "source_duration": duration,
        "added_duration": float(cover_info.get("duration") or 0) + float(outro_info.get("duration") or 0),
    }


def _generate_review_cover_step(context: dict) -> dict:
    title = _review_pack_title(context)
    subtitle = _review_pack_subtitle(context)
    pipeline = str(context.get("pipeline") or context.get("template_key") or "")
    cover_dir = get_settings().work_dir / "covers" / f"run_{context['run_id']}"
    cover_dir.mkdir(parents=True, exist_ok=True)
    image_path = cover_dir / "review_cover.png"
    segment_path = cover_dir / "review_cover.mp4"
    if not _cover_enabled(context):
        return {"enabled": False, "title": title, "subtitle": subtitle}
    segments, cover_info = _prepend_review_cover(
        context,
        title=title,
        subtitle=subtitle,
        pipeline=pipeline,
        rendered_segments=[],
    )
    segment = segments[0] if segments else segment_path
    context["review_cover_segment"] = segment
    context["review_cover_info"] = cover_info
    return {
        **cover_info,
        "title": title,
        "subtitle": subtitle,
        "segment_path": str(segment),
    }


def _generate_outro_cta_step(context: dict) -> dict:
    title = _review_pack_title(context)
    pipeline = str(context.get("pipeline") or context.get("template_key") or "")
    outro_dir = get_settings().work_dir / "outros" / f"run_{context['run_id']}"
    outro_dir.mkdir(parents=True, exist_ok=True)
    segment_path = outro_dir / "full_episode_cta.mp4"
    if not _outro_enabled(context):
        return {"enabled": False, "title": "点击左下角", "subtitle": "观看全集"}
    segments, outro_info = _append_full_episode_cta(
        context,
        title=title,
        pipeline=pipeline,
        rendered_segments=[],
    )
    segment = segments[-1] if segments else segment_path
    context["outro_cta_segment"] = segment
    context["outro_cta_info"] = outro_info
    return {
        **outro_info,
        "segment_path": str(segment),
    }


def _asset_duration_with_pack(duration: object, review_pack: dict) -> float | None:
    try:
        base = float(duration)
    except (TypeError, ValueError):
        base = float(review_pack.get("source_duration") or 0)
    if base <= 0:
        return None
    return base + float(review_pack.get("added_duration") or 0)


def _review_pack_title(context: dict) -> str:
    template_key = str(context.get("template_key") or "")
    artifacts = context.get("artifacts") or {}
    inferred_title = _infer_drama_display_title(context)
    if template_key == "story_quality_cut":
        return inferred_title
    if template_key == "story_promo_mix":
        return inferred_title
    video = context.get("video") or {}
    if template_key == "promo_variants":
        return _clean_source_title(str(video.get("name") or "")) or inferred_title
    if template_key == "promo_single":
        return _clean_source_title(str(video.get("name") or "")) or inferred_title
    if artifacts.get("plan_story_promo_mix"):
        return inferred_title
    return _clean_source_title(str(video.get("name") or "")) or inferred_title


def _review_pack_subtitle(context: dict) -> str:
    template_key = str(context.get("template_key") or "")
    artifacts = context.get("artifacts") or {}
    title = _review_pack_title(context)
    if template_key == "story_quality_cut":
        plan = artifacts.get("validate_quality_edit_decisions") or {}
        return _promo_copy(
            title,
            "quality_cut",
            storyline=_quality_cut_viewer_storyline(plan),
            pipeline="story_quality_cut",
        )["promo_copy"]
    if template_key == "story_promo_mix":
        review = artifacts.get("render_story_promo_mix") or {}
        storyline = (review.get("result") or {}).get("edit_review", {}).get("storyline") or ""
        return _promo_copy(title, "promo", storyline=storyline, pipeline="story_promo_mix")["promo_copy"]
    if template_key in {"promo_single", "promo_variants"}:
        return _promo_copy(title, "promo", pipeline=template_key)["promo_copy"]
    return _promo_copy(title, "highlight", pipeline="highlight_clip")["promo_copy"]


def _quality_cut_viewer_storyline(plan: dict) -> str:
    kept_segments = plan.get("kept_segments") or plan.get("decisions") or []
    candidates = []
    for field in (
        plan.get("storyline"),
        plan.get("summary"),
        plan.get("quality_notes"),
        (plan.get("model_review") or {}).get("summary"),
        (plan.get("model_review") or {}).get("quality_notes"),
    ):
        candidates.extend(_story_candidate_sentences(str(field or "")))
    for item in kept_segments:
        reason = str(item.get("reason") or item.get("role") or "").strip()
        candidates.extend(_story_candidate_sentences(reason))
    if not candidates:
        return ""
    candidates.sort(key=lambda item: (-item[0], len(item[1])))
    first = candidates[0][1]
    second = next((sentence for _, sentence in candidates[1:] if sentence != first), "")
    if second and len(first) + len(second) <= 38:
        return f"{first}，{second}。"
    return first.rstrip("，,") + "。"


def _infer_drama_display_title(context: dict) -> str:
    project_title = _clean_source_title(str((context.get("project") or {}).get("name") or ""))
    if project_title:
        return project_title
    videos = context.get("videos") or []
    names = [str(video.get("name") or "") for video in videos if video.get("name")]
    video = context.get("video") or {}
    if video.get("name"):
        names.append(str(video["name"]))
    cleaned = [_clean_source_title(name) for name in names]
    cleaned = [name for name in cleaned if name and name not in INTERNAL_REVIEW_TITLES]
    if not cleaned:
        return "短剧高能片段"
    prefix = _common_title_prefix(cleaned)
    if prefix:
        return prefix
    shortest = min(cleaned, key=len)
    return shortest[:18] if shortest else "短剧高能片段"


def _clean_source_title(name: str) -> str:
    title = Path(name).stem.strip()
    if re.fullmatch(r"\d+(\(\d+\))?", title):
        return ""
    title = re.sub(r"[_\-\s]*(第?\s*\d+\s*[集话話部期]|EP?\s*\d+|episode\s*\d+)\s*$", "", title, flags=re.IGNORECASE)
    title = re.sub(r"[_\-\s]*(上|中|下)\s*$", "", title)
    title = re.sub(r"[_\-\s]*(原片|素材|成片|高清|竖屏|横屏|剪辑版|无水印)\s*$", "", title, flags=re.IGNORECASE)
    title = re.sub(r"[\s_\-]+", " ", title).strip(" -_")
    return title[:24]


def _common_title_prefix(names: list[str]) -> str:
    if len(names) < 2:
        return names[0]
    prefix = names[0]
    for name in names[1:]:
        while prefix and not name.startswith(prefix):
            prefix = prefix[:-1]
        if not prefix:
            break
    prefix = prefix.strip(" -_")
    if len(prefix) >= 2:
        return prefix[:18]
    return ""


def _review_pack_story_context(context: dict) -> str:
    artifacts = context.get("artifacts") or {}
    videos = context.get("videos") or []
    parts = []
    source_names = [str(video.get("name") or "") for video in videos if video.get("name")]
    if source_names:
        parts.append("素材列表：" + "、".join(source_names[:8]))
    for key in ("model_watch_quality_cut", "validate_quality_edit_decisions", "plan_story_quality_cut"):
        content = artifacts.get(key) or {}
        summary = str(content.get("summary") or content.get("quality_notes") or "").strip()
        if summary:
            parts.append(f"{key}总结：{summary[:420]}")
        risks = [str(item).strip() for item in content.get("risks") or content.get("quality_risks") or [] if str(item).strip()]
        if risks:
            parts.append("风险/悬念：" + "；".join(risks[:4])[:360])
    kept_segments = _review_pack_kept_segments(context)
    if kept_segments:
        descriptions = []
        for item in kept_segments[:10]:
            reason = str(item.get("reason") or item.get("role") or "").strip()
            name = str(item.get("source_video_name") or "").strip()
            descriptions.append(f"{name} {item.get('start')}-{item.get('end')}秒：{reason[:80]}")
        parts.append("保留剧情片段：" + "；".join(descriptions))
    if not parts:
        title = _review_pack_title(context)
        subtitle = _review_pack_subtitle(context)
        parts.append(f"短剧标题：{title}。观众文案：{subtitle}")
    return "\n".join(parts)


def _review_pack_kept_segments(context: dict) -> list[dict]:
    artifacts = context.get("artifacts") or {}
    for key in ("validate_quality_edit_decisions", "plan_story_quality_cut"):
        content = artifacts.get(key) or {}
        segments = content.get("kept_segments") or []
        if segments:
            return list(segments)
    decisions = (artifacts.get("model_watch_quality_cut") or {}).get("decisions") or []
    return [item for item in decisions if item.get("decision") != "drop"]


def _review_pack_reference_frame(context: dict) -> Path | None:
    cached = context.get("review_pack_reference_frame")
    if cached and Path(cached).exists():
        return Path(cached)
    frame_dir = get_settings().work_dir / "review-frames" / f"run_{context['run_id']}"
    candidates = _review_pack_kept_segments(context)
    for index, item in enumerate(candidates[:8], start=1):
        source_path = item.get("source_path")
        if not source_path:
            source_video_id = item.get("source_video_id")
            source = next((video for video in context.get("videos") or [] if video.get("id") == source_video_id), None)
            source_path = (source or {}).get("path")
        if not source_path:
            continue
        try:
            start = float(item.get("start") or 0)
            end = float(item.get("end") or 0)
        except (TypeError, ValueError):
            continue
        if end <= start:
            continue
        try:
            output_dir = frame_dir / f"candidate_{index:02d}"
            frames = extract_keyframes(Path(source_path), output_dir, start, end, count=1)
        except Exception:
            continue
        if frames and frames[0].exists():
            context["review_pack_reference_frame"] = str(frames[0])
            return frames[0]
    for video in context.get("videos") or []:
        source_path = video.get("path")
        duration = float(video.get("duration") or 0)
        if not source_path or duration <= 1:
            continue
        try:
            frames = extract_keyframes(Path(source_path), frame_dir / f"source_{video['id']}", duration * 0.2, min(duration, duration * 0.2 + 1), count=1)
        except Exception:
            continue
        if frames and frames[0].exists():
            context["review_pack_reference_frame"] = str(frames[0])
            return frames[0]
    return None


class Processor:
    def __init__(self, key: str, name: str, handler: Callable[[dict], dict]):
        self.key = key
        self.name = name
        self.handler = handler


PROCESSORS = {
    "probe_video": Processor("probe_video", "读取素材信息", lambda context: {"video": context["video"]}),
    "probe_source_collection": Processor("probe_source_collection", "读取素材集合", lambda context: _probe_source_collection(context)),
    "create_proxy_videos": Processor("create_proxy_videos", "生成低清代理视频", lambda context: _create_proxy_videos(context)),
    "detect_highlight_candidates": Processor("detect_highlight_candidates", "识别高光候选", lambda context: _detect_candidates(context)),
    "score_highlight_candidates": Processor("score_highlight_candidates", "模型复评候选", lambda context: _score_candidates(context)),
    "render_highlight_clips": Processor("render_highlight_clips", "渲染高光切片", lambda context: _render_highlight_clips(context)),
    "plan_promo_single": Processor("plan_promo_single", "规划引流视频", lambda context: _plan_promo_single(context)),
    "render_promo_single": Processor("render_promo_single", "渲染引流视频", lambda context: _render_promo_single(context)),
    "plan_promo_variants": Processor("plan_promo_variants", "规划多版本引流视频", lambda context: _plan_promo_variants(context)),
    "render_promo_variants": Processor("render_promo_variants", "渲染多版本引流视频", lambda context: _render_promo_variants(context)),
    "plan_story_promo_mix": Processor("plan_story_promo_mix", "规划剧情引流总剪", lambda context: _plan_story_promo_mix(context)),
    "generate_review_cover": Processor("generate_review_cover", "生成首秒封面", lambda context: _generate_review_cover_step(context)),
    "generate_outro_cta": Processor("generate_outro_cta", "生成片尾引导", lambda context: _generate_outro_cta_step(context)),
    "render_story_promo_mix": Processor("render_story_promo_mix", "渲染剧情引流总剪", lambda context: _render_story_promo_mix(context)),
    "plan_story_quality_cut": Processor("plan_story_quality_cut", "规划剧情精剪", lambda context: _plan_story_quality_cut(context)),
    "model_watch_quality_cut": Processor("model_watch_quality_cut", "模型审片剧情精剪", lambda context: _model_watch_quality_cut(context)),
    "validate_quality_edit_decisions": Processor("validate_quality_edit_decisions", "校验剧情精剪决策", lambda context: _validate_quality_edit_decisions(context)),
    "render_story_quality_cut": Processor("render_story_quality_cut", "渲染剧情精剪", lambda context: _render_story_quality_cut(context)),
}


PIPELINE_TEMPLATES = {
    "highlight_clip": {
        "key": "highlight_clip",
        "name": "高光切片",
        "description": "单个原视频生成多个高光切片。",
        "input_scope": "single_video",
        "output_cardinality": "many",
        "run_strategy": "per_source",
        "steps": ["probe_video", "detect_highlight_candidates", "score_highlight_candidates", "render_highlight_clips"],
        "params_schema": {},
    },
    "promo_single": {
        "key": "promo_single",
        "name": "引流视频",
        "description": "单个原视频生成一个剧情引流视频。",
        "input_scope": "single_video",
        "output_cardinality": "one",
        "run_strategy": "per_source",
        "steps": ["probe_video", "plan_promo_single", "generate_review_cover", "generate_outro_cta", "render_promo_single"],
        "params_schema": {
            "windows_per_video": {"type": "number", "label": "候选窗口数", "default": 3},
        },
    },
    "promo_variants": {
        "key": "promo_variants",
        "name": "引流多版本",
        "description": "单个原视频生成多个剧情引流视频版本。",
        "input_scope": "single_video",
        "output_cardinality": "many",
        "run_strategy": "per_source",
        "steps": ["probe_video", "plan_promo_variants", "generate_review_cover", "generate_outro_cta", "render_promo_variants"],
        "params_schema": {
            "windows_per_video": {"type": "number", "label": "候选窗口数", "default": 3},
        },
    },
    "story_promo_mix": {
        "key": "story_promo_mix",
        "name": "剧情引流总剪",
        "description": "多个原视频合成一个剧情概览引流视频，优先提取高能点、冲突点和悬念点。",
        "input_scope": "multi_video",
        "output_cardinality": "one",
        "run_strategy": "aggregate",
        "steps": ["probe_source_collection", "plan_story_promo_mix", "generate_review_cover", "generate_outro_cta", "render_story_promo_mix"],
        "params_schema": {
            "target_duration_seconds": {"type": "number", "label": "目标时长秒", "default": 90},
            "windows_per_video": {"type": "number", "label": "每集候选窗口数", "default": 2},
        },
    },
    "story_quality_cut": {
        "key": "story_quality_cut",
        "name": "剧情精剪",
        "description": "删除低质量和无剧情推进片段，保留有用剧情。时长由剧情质量决定。",
        "input_scope": "multi_video",
        "output_cardinality": "one",
        "run_strategy": "aggregate",
        "steps": [
            "create_proxy_videos",
            "model_watch_quality_cut",
            "validate_quality_edit_decisions",
            "generate_review_cover",
            "generate_outro_cta",
            "render_story_quality_cut",
        ],
        "params_schema": {
            "keep_policy": {
                "type": "select",
                "label": "保留策略",
                "default": "balanced",
                "options": ["strict", "balanced", "loose"],
            },
            "proxy_max_height": {
                "type": "number",
                "label": "代理视频最大高度",
                "default": 480,
            },
            "proxy_fps": {
                "type": "number",
                "label": "代理视频帧率",
                "default": 12,
            },
        },
    },
}


def list_pipeline_templates() -> list[dict]:
    return list(PIPELINE_TEMPLATES.values())


def get_pipeline_template(template_key: str) -> dict:
    template = PIPELINE_TEMPLATES.get(template_key)
    if not template:
        raise HTTPException(status_code=404, detail="pipeline template not found")
    return template


def list_pipeline_runs(project_id: int) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
                r.*,
                v.name AS source_video_name,
                COUNT(s.id) AS source_count
            FROM pipeline_runs r
            LEFT JOIN videos v ON v.id = r.source_video_id
            LEFT JOIN pipeline_run_sources s ON s.run_id = r.id
            WHERE r.project_id = ?
            GROUP BY r.id
            ORDER BY r.created_at DESC, r.id DESC
            """,
            (project_id,),
        ).fetchall()
    return [_normalize_run(row) for row in rows_to_dicts(rows)]


def get_pipeline_run(run_id: int, project_id: int | None = None) -> dict:
    with connect() as conn:
        if project_id is None:
            row = conn.execute(
                """
                SELECT
                    r.*,
                    v.name AS source_video_name,
                    COUNT(s.id) AS source_count
                FROM pipeline_runs r
                LEFT JOIN videos v ON v.id = r.source_video_id
                LEFT JOIN pipeline_run_sources s ON s.run_id = r.id
                WHERE r.id = ?
                GROUP BY r.id
                """,
                (run_id,),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT
                    r.*,
                    v.name AS source_video_name,
                    COUNT(s.id) AS source_count
                FROM pipeline_runs r
                LEFT JOIN videos v ON v.id = r.source_video_id
                LEFT JOIN pipeline_run_sources s ON s.run_id = r.id
                WHERE r.id = ? AND r.project_id = ?
                GROUP BY r.id
                """,
                (run_id, project_id),
            ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="pipeline run not found")
    run = _normalize_run(dict(row))
    run["steps"] = list_pipeline_steps(run_id, project_id=project_id)
    run["sources"] = list_pipeline_run_sources(run_id, project_id=project_id)
    return run


def list_pipeline_run_sources(run_id: int, project_id: int | None = None) -> list[dict]:
    _ensure_pipeline_run(run_id, project_id=project_id)
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT s.*, v.name AS source_video_name
            FROM pipeline_run_sources s
            LEFT JOIN videos v ON v.id = s.source_video_id
            WHERE s.run_id = ?
            ORDER BY s.order_index, s.id
            """,
            (run_id,),
        ).fetchall()
    return rows_to_dicts(rows)


def list_pipeline_artifacts(run_id: int, project_id: int | None = None) -> list[dict]:
    _ensure_pipeline_run(run_id, project_id=project_id)
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM artifacts
            WHERE pipeline_run_id = ?
            ORDER BY created_at, id
            """,
            (run_id,),
        ).fetchall()
    return [_normalize_artifact(row) for row in rows_to_dicts(rows)]


def list_pipeline_generated_assets(run_id: int, project_id: int | None = None) -> list[dict]:
    _ensure_pipeline_run(run_id, project_id=project_id)
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT a.*, v.name AS source_video_name
            FROM generated_assets a
            LEFT JOIN videos v ON v.id = a.source_video_id
            WHERE a.pipeline_run_id = ?
            ORDER BY a.created_at DESC, a.id DESC
            """,
            (run_id,),
        ).fetchall()
    return [_normalize_asset(row) for row in rows_to_dicts(rows)]


def list_pipeline_steps(run_id: int, project_id: int | None = None) -> list[dict]:
    _ensure_pipeline_run(run_id, project_id=project_id)
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM pipeline_steps WHERE run_id = ? ORDER BY order_index",
            (run_id,),
        ).fetchall()
    return [_normalize_step(row) for row in rows_to_dicts(rows)]


def create_and_execute_pipeline_runs(project_id: int, payload: PipelineRunCreate) -> dict:
    runs = create_pipeline_runs(project_id, payload)
    executed = []
    for run in runs["runs"]:
        try:
            _execute_existing_run(run["id"])
        except Exception:
            pass
        executed.append(get_pipeline_run(run["id"]))
    return {"runs": executed}


def create_pipeline_runs(project_id: int, payload: PipelineRunCreate, enqueue: bool = False) -> dict:
    template = PIPELINE_TEMPLATES.get(payload.template_key)
    if not template:
        raise HTTPException(status_code=400, detail=f"unknown pipeline template: {payload.template_key}")
    source_video_ids = payload.resolved_source_video_ids()
    if not source_video_ids:
        raise HTTPException(status_code=400, detail="source_video_ids is required")
    source_video_ids = _dedupe_ids(source_video_ids)
    run_strategy = template.get("run_strategy") or "per_source"
    if run_strategy == "aggregate":
        videos = [_get_project_video(project_id, source_video_id) for source_video_id in source_video_ids]
        prompt_snapshot = _snapshot_prompt_configs(payload.prompt_config_ids)
        primary_video_id = videos[0]["id"] if videos else None
        run_id = _create_run(project_id, primary_video_id, template["key"], payload.params, prompt_snapshot)
        _create_run_sources(run_id, project_id, [video["id"] for video in videos])
        _create_steps(run_id, project_id, primary_video_id, template)
        if enqueue:
            enqueue_pipeline_run(run_id)
        return {"runs": [get_pipeline_run(run_id)]}
    if run_strategy != "per_source":
        raise HTTPException(status_code=400, detail=f"unsupported run strategy: {run_strategy}")
    runs = []
    for source_video_id in source_video_ids:
        video = _get_project_video(project_id, source_video_id)
        prompt_snapshot = _snapshot_prompt_configs(payload.prompt_config_ids)
        run_id = _create_run(project_id, video["id"], template["key"], payload.params, prompt_snapshot)
        _create_run_sources(run_id, project_id, [video["id"]])
        _create_steps(run_id, project_id, video["id"], template)
        if enqueue:
            enqueue_pipeline_run(run_id)
        runs.append(get_pipeline_run(run_id))
    return {"runs": runs}


def create_and_execute_pipeline_run(project_id: int, payload: PipelineRunCreate) -> dict:
    result = create_and_execute_pipeline_runs(project_id, payload)
    runs = result["runs"]
    if len(runs) != 1:
        return result
    return runs[0]


def cancel_pipeline_run(run_id: int, project_id: int | None = None) -> dict:
    run = _ensure_pipeline_run(run_id, project_id=project_id)
    if run["status"] == "pending":
        with connect() as conn:
            conn.execute(
                """
                UPDATE pipeline_runs
                SET status = 'canceled',
                    finished_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (run_id,),
            )
            conn.execute(
                "UPDATE pipeline_steps SET status = 'skipped' WHERE run_id = ? AND status = 'pending'",
                (run_id,),
            )
            conn.execute(
                """
                UPDATE pipeline_jobs
                SET status = 'canceled',
                    updated_at = CURRENT_TIMESTAMP
                WHERE run_id = ? AND status = 'pending'
                """,
                (run_id,),
            )
        return get_pipeline_run(run_id, project_id=project_id)
    if run["status"] in {"succeeded", "failed", "canceled"}:
        return get_pipeline_run(run_id, project_id=project_id)
    raise HTTPException(status_code=409, detail="running synchronous pipeline runs cannot be canceled yet")


def enqueue_pipeline_run(run_id: int, priority: int = 100) -> dict:
    _ensure_pipeline_run(run_id)
    with connect() as conn:
        row = conn.execute("SELECT * FROM pipeline_jobs WHERE run_id = ?", (run_id,)).fetchone()
        if row:
            return _normalize_job(dict(row))
        cursor = conn.execute(
            """
            INSERT INTO pipeline_jobs (run_id, status, priority)
            VALUES (?, 'pending', ?)
            """,
            (run_id, priority),
        )
        job_id = int(cursor.lastrowid)
        job = conn.execute("SELECT * FROM pipeline_jobs WHERE id = ?", (job_id,)).fetchone()
    return _normalize_job(dict(job))


def list_pipeline_jobs(status: str | None = None) -> list[dict]:
    with connect() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM pipeline_jobs WHERE status = ? ORDER BY priority ASC, created_at ASC, id ASC",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM pipeline_jobs ORDER BY created_at DESC, id DESC").fetchall()
    return [_normalize_job(row) for row in rows_to_dicts(rows)]


def run_next_pipeline_job(worker_id: str | None = None) -> dict:
    worker = worker_id or socket.gethostname()
    with connect() as conn:
        conn.execute(
            """
            UPDATE pipeline_jobs
            SET status = 'pending',
                locked_by = '',
                locked_at = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE status = 'running'
              AND locked_at IS NOT NULL
              AND locked_at < datetime('now', ?)
            """,
            (f"-{STALE_PIPELINE_JOB_MINUTES} minutes",),
        )
        cursor = conn.execute(
            """
            UPDATE pipeline_jobs
            SET status = 'running',
                locked_by = ?,
                locked_at = CURRENT_TIMESTAMP,
                attempts = attempts + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = (
                SELECT id
                FROM pipeline_jobs
                WHERE status = 'pending'
                ORDER BY priority ASC, created_at ASC, id ASC
                LIMIT 1
            )
            RETURNING *
            """,
            (worker,),
        )
        row = cursor.fetchone()
        if not row:
            return {"status": "idle"}
        job = dict(row)
    try:
        run = _execute_existing_run(job["run_id"])
        with connect() as conn:
            conn.execute(
                """
                UPDATE pipeline_jobs
                SET status = 'succeeded',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (job["id"],),
            )
        return {"status": "succeeded", "job_id": job["id"], "run": run}
    except Exception as exc:
        with connect() as conn:
            conn.execute(
                """
                UPDATE pipeline_jobs
                SET status = 'failed',
                    error = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (str(exc), job["id"]),
            )
            conn.execute(
                """
                UPDATE pipeline_runs
                SET status = 'failed',
                    error = ?,
                    finished_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status IN ('pending', 'running')
                """,
                (str(exc), job["run_id"]),
            )
            conn.execute(
                """
                UPDATE pipeline_steps
                SET status = 'skipped'
                WHERE run_id = ? AND status = 'pending'
                """,
                (job["run_id"],),
            )
        return {"status": "failed", "job_id": job["id"], "error": str(exc)}


def _create_run(project_id: int, source_video_id: int | None, template_key: str, params: dict, prompt_snapshot: dict) -> int:
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO pipeline_runs
                (project_id, source_video_id, template_key, status, params_json, prompt_snapshot_json)
            VALUES
                (?, ?, ?, 'pending', ?, ?)
            """,
            (
                project_id,
                source_video_id,
                template_key,
                json.dumps(params or {}, ensure_ascii=False),
                json.dumps(prompt_snapshot or {}, ensure_ascii=False),
            ),
        )
        return int(cursor.lastrowid)


def _create_run_sources(run_id: int, project_id: int, source_video_ids: list[int]) -> None:
    with connect() as conn:
        for index, source_video_id in enumerate(source_video_ids, start=1):
            conn.execute(
                """
                INSERT INTO pipeline_run_sources
                    (run_id, project_id, source_video_id, order_index)
                VALUES
                    (?, ?, ?, ?)
                """,
                (run_id, project_id, source_video_id, index),
            )


def _create_steps(run_id: int, project_id: int, source_video_id: int | None, template: dict) -> None:
    with connect() as conn:
        for index, step_key in enumerate(template["steps"], start=1):
            processor = PROCESSORS[step_key]
            conn.execute(
                """
                INSERT INTO pipeline_steps
                    (run_id, project_id, source_video_id, step_key, name, order_index, status)
                VALUES
                    (?, ?, ?, ?, ?, ?, 'pending')
                """,
                (run_id, project_id, source_video_id, step_key, processor.name, index),
            )


def _execute_existing_run(run_id: int) -> dict:
    run = _ensure_pipeline_run(run_id)
    template = PIPELINE_TEMPLATES.get(run["template_key"])
    if not template:
        raise HTTPException(status_code=400, detail=f"unknown pipeline template: {run['template_key']}")
    project_id = int(run["project_id"])
    sources = _get_run_source_videos(project_id, run_id)
    if template.get("run_strategy") == "aggregate":
        if not sources:
            raise HTTPException(status_code=400, detail="pipeline run has no source videos")
        video = sources[0]
    else:
        video = _get_project_video(project_id, int(run["source_video_id"]))
        if not sources:
            sources = [video]
    _execute_run(run_id, template, video, sources, _loads(run.get("params_json")), _loads(run.get("prompt_snapshot_json")))
    return get_pipeline_run(run_id)


def _execute_run(run_id: int, template: dict, video: dict, videos: list[dict], params: dict, prompt_snapshot: dict) -> None:
    project = _get_project(video["project_id"])
    context = {
        "run_id": run_id,
        "project_id": video["project_id"],
        "project": project,
        "template_key": template["key"],
        "pipeline": template["key"],
        "video": video,
        "videos": videos,
        "params": params or {},
        "prompt_snapshot": prompt_snapshot or {},
        "artifacts": {},
        "generated_assets": [],
    }
    with connect() as conn:
        conn.execute(
            "UPDATE pipeline_runs SET status = 'running', started_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (run_id,),
        )
    steps = list_pipeline_steps(run_id)
    try:
        for index, step in enumerate(steps, start=1):
            processor = PROCESSORS[step["step_key"]]
            if step["status"] == "succeeded":
                output = _loads(step.get("output_json"))
                context["artifacts"][processor.key] = output
                _restore_step_context(context, processor.key, output)
                continue
            _mark_step_running(step["id"], context)
            output = processor.handler(context)
            context["artifacts"][processor.key] = output
            _record_artifact(context, step["id"], processor.key, processor.name, content=output)
            _mark_step_succeeded(step["id"], output)
            progress = int(index / max(len(steps), 1) * 100)
            _update_run_progress(run_id, processor.key, progress)
        result = {"asset_ids": [asset["id"] for asset in context.get("generated_assets", [])]}
        with connect() as conn:
            conn.execute(
                """
                UPDATE pipeline_runs
                SET status = 'succeeded',
                    progress = 100,
                    result_json = ?,
                    finished_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (json.dumps(result, ensure_ascii=False), run_id),
            )
    except Exception as exc:  # noqa: BLE001 - store pipeline failure for UI inspection.
        with connect() as conn:
            conn.execute(
                """
                UPDATE pipeline_runs
                SET status = 'failed',
                    error = ?,
                    finished_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (str(exc), run_id),
            )
        raise


def _restore_step_context(context: dict, step_key: str, output: dict) -> None:
    if step_key == "generate_review_cover":
        segment_path = output.get("segment_path")
        if segment_path:
            context["review_cover_segment"] = Path(segment_path)
        context["review_cover_info"] = output
    elif step_key == "generate_outro_cta":
        segment_path = output.get("segment_path")
        if segment_path:
            context["outro_cta_segment"] = Path(segment_path)
        context["outro_cta_info"] = output


def _detect_candidates(context: dict) -> dict:
    video = context["video"]
    suggestions = suggest_audio_peak_clips(Path(video["path"]), float(video.get("duration") or 0))
    return {"suggestions": suggestions}


def _score_candidates(context: dict) -> dict:
    video = context["video"]
    suggestions = (context["artifacts"].get("detect_highlight_candidates") or {}).get("suggestions") or []
    suggestions, model_review = enrich_suggestions_with_ai(video, suggestions)
    return {"suggestions": suggestions, "model_review": model_review}


def _render_highlight_clips(context: dict) -> dict:
    video = context["video"]
    source = Path(video["path"])
    scored = context["artifacts"].get("score_highlight_candidates") or {}
    suggestions = scored.get("suggestions") or []
    generated = []
    for suggestion in suggestions:
        output = get_settings().output_dir / (
            f"{source.stem.replace(' ', '_')}_pipe_{context['run_id']}_{format_time(suggestion['start'])}_{format_time(suggestion['end'])}.mp4"
        )
        cut_clip(source, output, suggestion["start"], suggestion["end"])
        with connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO clips
                    (video_id, start_seconds, end_seconds, score, reason, output_path, status)
                VALUES
                    (?, ?, ?, ?, ?, ?, 'exported')
                """,
                (
                    video["id"],
                    suggestion["start"],
                    suggestion["end"],
                    suggestion["score"],
                    suggestion.get("reason", ""),
                    str(output),
                ),
            )
            clip_id = int(cursor.lastrowid)
        asset = record_generated_asset(
            project_id=context["project_id"],
            source_video_id=video["id"],
            clip_id=clip_id,
            pipeline_run_id=context["run_id"],
            pipeline_step_id=context.get("current_step_id"),
            asset_type="highlight",
            title=f"{video['name']} 高光片段",
            description=suggestion.get("reason", ""),
            output_path=output,
            download_url=f"/api/clips/{clip_id}/download",
            duration=suggestion["end"] - suggestion["start"],
            metadata={
                "pipeline": "highlight_clip",
                "suggestion": suggestion,
                "model_review": scored.get("model_review"),
                **_promo_copy(f"{video['name']} 高光片段", "highlight", pipeline="highlight_clip"),
            },
        )
        context["generated_assets"].append(asset)
        generated.append(asset)
    return {"generated": generated}


def _plan_promo_single(context: dict) -> dict:
    windows = int((context["params"] or {}).get("windows_per_video") or 3)
    return {"limit": 1, "windows_per_video": max(1, min(4, windows)), "variant_mode": "single"}


def _plan_promo_variants(context: dict) -> dict:
    windows = int((context["params"] or {}).get("windows_per_video") or 3)
    return {"limit": 1, "windows_per_video": max(1, min(4, windows)), "variant_mode": "all"}


def _render_promo_single(context: dict) -> dict:
    video = context["video"]
    plan = context["artifacts"].get("plan_promo_single") or {}
    result = generate_promo_video([video], limit=1, windows_per_video=plan.get("windows_per_video", 3), variant_mode="single")
    if result.get("status") != "exported":
        return result
    generated = []
    variants = result.get("variants") or []
    storyline = (result.get("edit_review") or {}).get("storyline") or ""
    for variant in variants:
        output_path = variant.get("output_path")
        if not output_path:
            continue
        title = variant.get("label") or variant.get("title") or "引流视频"
        copy_meta = _promo_copy(title, "promo", storyline=storyline, pipeline="promo_single")
        review_pack = _wrap_existing_output_with_review_pack(
            context,
            output_path=Path(output_path),
            title=title,
            subtitle=copy_meta["promo_copy"],
            pipeline="promo_single",
        )
        asset = record_generated_asset(
            project_id=context["project_id"],
            source_video_id=video["id"],
            pipeline_run_id=context["run_id"],
            pipeline_step_id=context.get("current_step_id"),
            asset_type="promo",
            title=title,
            description=storyline,
            output_path=Path(output_path),
            download_url=variant.get("download_url") or result.get("download_url") or "/api/promos/latest/download",
            duration=_asset_duration_with_pack(variant.get("duration_estimate_seconds"), review_pack),
            metadata={
                "pipeline": "promo_single",
                "variant": variant,
                "result": result,
                **copy_meta,
                "review_pack": review_pack,
                "review_cover": review_pack.get("review_cover") or {},
                "outro_cta": review_pack.get("outro_cta") or {},
            },
        )
        context["generated_assets"].append(asset)
        generated.append(asset)
    return {"result": result, "generated": generated}


def _render_promo_variants(context: dict) -> dict:
    video = context["video"]
    plan = context["artifacts"].get("plan_promo_variants") or {}
    result = generate_promo_video([video], limit=1, windows_per_video=plan.get("windows_per_video", 3), variant_mode="all")
    if result.get("status") != "exported":
        return result
    generated = []
    variants = result.get("variants") or []
    storyline = (result.get("edit_review") or {}).get("storyline") or ""
    for variant in variants:
        output_path = variant.get("output_path")
        if not output_path:
            continue
        title = variant.get("label") or variant.get("title") or "引流视频"
        copy_meta = _promo_copy(title, "promo", storyline=storyline, pipeline="promo_variants")
        review_pack = _wrap_existing_output_with_review_pack(
            context,
            output_path=Path(output_path),
            title=title,
            subtitle=copy_meta["promo_copy"],
            pipeline="promo_variants",
        )
        asset = record_generated_asset(
            project_id=context["project_id"],
            source_video_id=video["id"],
            pipeline_run_id=context["run_id"],
            pipeline_step_id=context.get("current_step_id"),
            asset_type="promo",
            title=title,
            description=storyline,
            output_path=Path(output_path),
            download_url=variant.get("download_url") or result.get("download_url") or "/api/promos/latest/download",
            duration=_asset_duration_with_pack(variant.get("duration_estimate_seconds"), review_pack),
            metadata={
                "pipeline": "promo_variants",
                "variant": variant,
                "result": result,
                **copy_meta,
                "review_pack": review_pack,
                "review_cover": review_pack.get("review_cover") or {},
                "outro_cta": review_pack.get("outro_cta") or {},
            },
        )
        context["generated_assets"].append(asset)
        generated.append(asset)
    return {"result": result, "generated": generated}


def _probe_source_collection(context: dict) -> dict:
    videos = context.get("videos") or []
    return {
        "source_count": len(videos),
        "sources": [
            {
                "id": video["id"],
                "name": video["name"],
                "duration": video.get("duration"),
                "width": video.get("width"),
                "height": video.get("height"),
                "codec": video.get("codec"),
            }
            for video in videos
        ],
    }


def _create_proxy_videos(context: dict) -> dict:
    params = context.get("params") or {}
    videos = context.get("videos") or []
    proxy_max_height = _bounded_int(params.get("proxy_max_height"), default=480, minimum=240, maximum=720)
    proxy_fps = _bounded_int(params.get("proxy_fps"), default=12, minimum=6, maximum=24)
    proxy_dir = get_settings().work_dir / "proxy" / f"run_{context['run_id']}"
    proxies = []
    for order_index, video in enumerate(videos, start=1):
        source = Path(video["path"])
        output = proxy_dir / f"{order_index:03d}_{source.stem}_proxy.mp4"
        render_proxy_video(source, output, max_height=proxy_max_height, fps=proxy_fps)
        proxy_info = probe_video(output)
        proxies.append(
            {
                "source_video_id": video["id"],
                "source_video_name": video["name"],
                "source_path": str(source),
                "proxy_path": str(output),
                "order_index": order_index,
                "source_duration": video.get("duration"),
                "proxy_duration": proxy_info.get("duration"),
                "proxy_width": proxy_info.get("width"),
                "proxy_height": proxy_info.get("height"),
                "proxy_fps": proxy_info.get("fps"),
                "proxy_codec": proxy_info.get("codec"),
            }
        )
    return {
        "source_count": len(videos),
        "proxy_max_height": proxy_max_height,
        "proxy_fps": proxy_fps,
        "proxies": proxies,
        "mapping_note": "代理视频保留原始时间轴，后续模型 keep/drop 决策可按 timestamp 映射回原视频。",
    }


def _plan_story_promo_mix(context: dict) -> dict:
    params = context.get("params") or {}
    videos = context.get("videos") or []
    target_duration = int(params.get("target_duration_seconds") or 90)
    windows = int(params.get("windows_per_video") or 2)
    return {
        "source_count": len(videos),
        "target_duration_seconds": max(30, min(180, target_duration)),
        "windows_per_video": max(1, min(4, windows)),
        "variant_mode": "single",
        "strategy": "story_arc_mix",
    }


def _render_story_promo_mix(context: dict) -> dict:
    videos = context.get("videos") or []
    plan = context["artifacts"].get("plan_story_promo_mix") or {}
    if not videos:
        return {"status": "failed", "error": "no source videos"}
    result = generate_promo_video(
        videos,
        limit=len(videos),
        windows_per_video=plan.get("windows_per_video", 2),
        variant_mode="single",
        include_cards=False,
    )
    if result.get("status") != "exported":
        return result
    generated = []
    variants = result.get("variants") or []
    primary_video_id = videos[0]["id"]
    source_ids = [video["id"] for video in videos]
    storyline = (result.get("edit_review") or {}).get("storyline") or ""
    for variant in variants:
        output_path = variant.get("output_path")
        if not output_path:
            continue
        title = variant.get("label") or variant.get("title") or "剧情引流总剪"
        copy_meta = _promo_copy(title, "promo", storyline=storyline, pipeline="story_promo_mix")
        review_pack = _wrap_existing_output_with_review_pack(
            context,
            output_path=Path(output_path),
            title=title,
            subtitle=copy_meta["promo_copy"],
            pipeline="story_promo_mix",
        )
        asset = record_generated_asset(
            project_id=context["project_id"],
            source_video_id=primary_video_id,
            pipeline_run_id=context["run_id"],
            pipeline_step_id=context.get("current_step_id"),
            asset_type="promo",
            title=title,
            description=storyline,
            output_path=Path(output_path),
            download_url=variant.get("download_url") or result.get("download_url") or "/api/promos/latest/download",
            duration=_asset_duration_with_pack(variant.get("duration_estimate_seconds"), review_pack),
            metadata={
                "pipeline": "story_promo_mix",
                "source_video_ids": source_ids,
                "plan": plan,
                "variant": variant,
                "result": result,
                **copy_meta,
                "review_pack": review_pack,
                "review_cover": review_pack.get("review_cover") or {},
                "outro_cta": review_pack.get("outro_cta") or {},
            },
        )
        context["generated_assets"].append(asset)
        generated.append(asset)
    return {"result": result, "generated": generated, "source_video_ids": source_ids}


def _plan_story_quality_cut(context: dict) -> dict:
    params = context.get("params") or {}
    keep_policy = str(params.get("keep_policy") or "balanced")
    if keep_policy not in {"strict", "balanced", "loose"}:
        keep_policy = "balanced"
    videos = context.get("videos") or []
    proxy_result = context["artifacts"].get("create_proxy_videos") or {}
    proxies_by_source_id = {
        int(proxy["source_video_id"]): proxy
        for proxy in proxy_result.get("proxies") or []
        if proxy.get("source_video_id") is not None
    }
    decisions = []
    for video_index, video in enumerate(videos):
        duration = float(video.get("duration") or 0)
        windows = _quality_candidate_windows(duration, keep_policy)
        proxy = proxies_by_source_id.get(int(video["id"])) or {}
        for window_index, (start, end) in enumerate(windows):
            decisions.append(
                {
                    "source_video_id": video["id"],
                    "source_video_name": video["name"],
                    "source_path": video["path"],
                    "proxy_path": proxy.get("proxy_path"),
                    "start": start,
                    "end": end,
                    "decision": "keep_required" if keep_policy == "strict" else "keep_optional",
                    "role": "story_progression",
                    "reason": "MVP 本地候选窗口：保留可能推进剧情或承载冲突/反应的片段。",
                    "order_index": video_index * 1000 + window_index,
                }
            )
    return {
        "keep_policy": keep_policy,
        "source_count": len(videos),
        "proxy_videos": proxy_result.get("proxies") or [],
        "decisions": decisions,
        "estimated_output_seconds": round(sum(item["end"] - item["start"] for item in decisions), 3),
        "quality_notes": "MVP 已生成低清代理视频，但 keep/drop 仍使用本地窗口召回。下一步接入大模型审片。",
    }


def _model_watch_quality_cut(context: dict) -> dict:
    params = context.get("params") or {}
    keep_policy = str(params.get("keep_policy") or "balanced")
    if keep_policy not in {"strict", "balanced", "loose"}:
        keep_policy = "balanced"
    proxy_result = context["artifacts"].get("create_proxy_videos") or {}
    proxies = proxy_result.get("proxies") or []
    prompt_text = _prompt_snapshot_text(context.get("prompt_snapshot") or {}, "story_quality_cut_review")
    result = gemini_watch_story_quality_proxies(
        proxies,
        keep_policy=keep_policy,
        operator_prompt=prompt_text,
    )
    if not result.get("ok"):
        fallback = _plan_story_quality_cut(context)
        return {
            "ok": False,
            "mode": "fallback_local_windows",
            "error": result.get("error") or "model watch failed",
            "model_result": result,
            "fallback_plan": fallback,
            "decisions": fallback.get("decisions") or [],
            "quality_notes": fallback.get("quality_notes") or "",
        }
    decisions = result.get("decisions") or []
    return {
        "ok": True,
        "mode": "model_proxy_review",
        "provider": "gemini",
        "summary": result.get("summary") or "",
        "quality_notes": result.get("quality_notes") or "",
        "risks": result.get("risks") or [],
        "raw_content": result.get("raw_content"),
        "decisions": decisions,
        "proxy_videos": proxies,
    }


def _validate_quality_edit_decisions(context: dict) -> dict:
    review = context["artifacts"].get("model_watch_quality_cut") or {}
    proxy_result = context["artifacts"].get("create_proxy_videos") or {}
    videos = context.get("videos") or []
    params = context.get("params") or {}
    keep_policy = str(params.get("keep_policy") or "balanced")
    if keep_policy not in {"strict", "balanced", "loose"}:
        keep_policy = "balanced"
    source_by_id = {int(video["id"]): video for video in videos}
    proxy_by_source_id = {
        int(proxy["source_video_id"]): proxy
        for proxy in proxy_result.get("proxies") or []
        if proxy.get("source_video_id") is not None
    }
    validated = []
    rejected = []
    for index, decision in enumerate(review.get("decisions") or [], start=1):
        normalized, error = _normalize_quality_decision(index, decision, source_by_id, proxy_by_source_id)
        if error:
            rejected.append({"decision": decision, "error": error})
            continue
        validated.append(normalized)
    if not validated:
        fallback = _plan_story_quality_cut(context)
        validated = [
            normalized
            for index, decision in enumerate(fallback.get("decisions") or [], start=1)
            for normalized, error in [_normalize_quality_decision(index, decision, source_by_id, proxy_by_source_id)]
            if not error
        ]
        review = {
            **review,
            "mode": "fallback_local_windows",
            "fallback_reason": "model decisions were empty or invalid",
        }
    merged = _merge_quality_decisions(validated)
    merged, quality_adjustments = _improve_quality_decisions(merged, keep_policy)
    kept = _kept_quality_decisions(merged, keep_policy)
    source_summaries = _quality_source_summaries(videos, merged, kept)
    return {
        "ok": bool(kept),
        "mode": review.get("mode") or "model_proxy_review",
        "keep_policy": keep_policy,
        "source_count": len(videos),
        "decisions": merged,
        "kept_segments": kept,
        "rejected_decisions": rejected,
        "quality_adjustments": quality_adjustments,
        "source_summaries": source_summaries,
        "quality_risks": _quality_risks(source_summaries, rejected, review),
        "estimated_output_seconds": round(sum(item["end"] - item["start"] for item in kept), 3),
        "model_review": review,
        "quality_notes": review.get("quality_notes") or review.get("summary") or "",
    }


def _render_story_quality_cut(context: dict) -> dict:
    plan = context["artifacts"].get("validate_quality_edit_decisions") or context["artifacts"].get("plan_story_quality_cut") or {}
    decisions = sorted(plan.get("kept_segments") or plan.get("decisions") or [], key=lambda item: item.get("order_index", 0))
    keep_policy = plan.get("keep_policy") or "balanced"
    kept = _kept_quality_decisions(decisions, keep_policy)
    if not kept:
        return {"status": "failed", "error": "no kept story segments", "plan": plan}

    settings = get_settings()
    clip_dir = settings.work_dir / "clips" / f"story_quality_cut_{context['run_id']}"
    clip_dir.mkdir(parents=True, exist_ok=True)
    rendered_segments = []
    for index, decision in enumerate(kept, start=1):
        source = Path(decision["source_path"])
        output = clip_dir / f"{index:03d}_{source.stem}_{format_time(float(decision['start']))}_{format_time(float(decision['end']))}.mp4"
        render_clip_segment(source, output, float(decision["start"]), float(decision["end"]))
        rendered_segments.append(output)

    final_output = settings.promo_dir / f"story_quality_cut_run_{context['run_id']}.mp4"
    display_title = _review_pack_title(context)
    copy_meta = _promo_copy(
        display_title,
        "quality_cut",
        storyline=_quality_cut_viewer_storyline(plan),
        pipeline="story_quality_cut",
    )
    cover_segment = context.get("review_cover_segment")
    cover_info = context.get("review_cover_info")
    if cover_segment and Path(cover_segment).exists():
        cover_info = cover_info or {
            "enabled": True,
            "mode": "pre_generated",
            "duration": REVIEW_COVER_DURATION_SECONDS,
            "segment_path": str(cover_segment),
        }
        rendered_segments = [Path(cover_segment), *rendered_segments]
    else:
        rendered_segments, cover_info = _prepend_review_cover(
            context,
            title=display_title,
            subtitle=copy_meta["promo_copy"],
            pipeline="story_quality_cut",
            rendered_segments=rendered_segments,
        )
    outro_segment = context.get("outro_cta_segment")
    outro_info = context.get("outro_cta_info")
    if outro_segment and Path(outro_segment).exists():
        outro_info = outro_info or {
            "enabled": True,
            "mode": "pre_generated",
            "duration": OUTRO_CTA_DURATION_SECONDS,
            "segment_path": str(outro_segment),
        }
        rendered_segments = [*rendered_segments, Path(outro_segment)]
    else:
        rendered_segments, outro_info = _append_full_episode_cta(
            context,
            title=display_title,
            pipeline="story_quality_cut",
            rendered_segments=rendered_segments,
        )
    concat_video_segments(rendered_segments, final_output)
    duration = (
        sum(float(decision["end"]) - float(decision["start"]) for decision in kept)
        + float(cover_info.get("duration") or 0)
        + float(outro_info.get("duration") or 0)
    )
    source_ids = [video["id"] for video in context.get("videos") or []]
    primary_video_id = source_ids[0] if source_ids else None
    asset = record_generated_asset(
        project_id=context["project_id"],
        source_video_id=primary_video_id,
        pipeline_run_id=context["run_id"],
        pipeline_step_id=context.get("current_step_id"),
        asset_type="quality_cut",
        title=f"{display_title} 剧情精剪" if display_title != "短剧高能片段" else "剧情精剪",
        description="删除低质量和无剧情推进片段后保留的剧情版本。",
        output_path=final_output,
        download_url=f"/api/promo-files/{final_output.name}/download",
        duration=duration,
        metadata={
            "pipeline": "story_quality_cut",
            "source_video_ids": source_ids,
            "keep_policy": keep_policy,
            "kept_segments": kept,
            "plan": plan,
            **copy_meta,
            "review_pack": {
                "enabled": bool(cover_info.get("enabled") or outro_info.get("enabled")),
                "review_cover": cover_info,
                "outro_cta": outro_info,
                "added_duration": float(cover_info.get("duration") or 0) + float(outro_info.get("duration") or 0),
            },
            "review_cover": cover_info,
            "outro_cta": outro_info,
        },
    )
    context["generated_assets"].append(asset)
    return {
        "status": "exported",
        "output_path": str(final_output),
        "download_url": asset["download_url"],
        "duration": duration,
        "kept_count": len(kept),
        "generated": [asset],
    }


def _quality_candidate_windows(duration: float, keep_policy: str) -> list[tuple[float, float]]:
    if duration <= 0:
        return []
    if keep_policy == "loose":
        window_seconds = 45.0
        max_windows = 6
    elif keep_policy == "strict":
        window_seconds = 24.0
        max_windows = 3
    else:
        window_seconds = 32.0
        max_windows = 4
    if duration <= window_seconds:
        return [(0.0, round(duration, 3))]
    points = [0.08, 0.32, 0.58, 0.82, 0.18, 0.72]
    windows = []
    for point in points[:max_windows]:
        center = duration * point
        start = max(0.0, center - window_seconds / 2)
        end = min(duration, start + window_seconds)
        start = max(0.0, end - window_seconds)
        candidate = (round(start, 3), round(end, 3))
        if not _overlaps_existing(candidate, windows):
            windows.append(candidate)
    return sorted(windows)


def _overlaps_existing(candidate: tuple[float, float], windows: list[tuple[float, float]]) -> bool:
    start, end = candidate
    for current_start, current_end in windows:
        overlap = max(0.0, min(end, current_end) - max(start, current_start))
        if overlap >= min(end - start, current_end - current_start) * 0.5:
            return True
    return False


def _normalize_quality_decision(
    index: int,
    decision: dict,
    source_by_id: dict[int, dict],
    proxy_by_source_id: dict[int, dict],
) -> tuple[dict | None, str | None]:
    try:
        source_video_id = int(decision.get("source_video_id"))
    except (TypeError, ValueError):
        return None, "invalid source_video_id"
    source = source_by_id.get(source_video_id)
    if not source:
        return None, f"source video {source_video_id} is not part of this run"
    try:
        start = float(decision.get("start"))
        end = float(decision.get("end"))
    except (TypeError, ValueError):
        return None, "invalid start or end"
    duration = float(source.get("duration") or 0)
    if duration <= 0:
        duration = float((proxy_by_source_id.get(source_video_id) or {}).get("proxy_duration") or 0)
    if duration <= 0:
        return None, "source duration is unavailable"
    start = max(0.0, min(duration, start))
    end = max(0.0, min(duration, end))
    if end - start < 0.8:
        return None, "segment is shorter than 0.8 seconds"
    label = str(decision.get("decision") or "").strip()
    if label not in {"keep_required", "keep_optional", "drop"}:
        label = "keep_optional"
    proxy = proxy_by_source_id.get(source_video_id) or {}
    return (
        {
            "source_video_id": source_video_id,
            "source_video_name": source.get("name") or decision.get("source_video_name") or "",
            "source_path": source.get("path"),
            "proxy_path": proxy.get("proxy_path") or decision.get("proxy_path"),
            "start": round(start, 3),
            "end": round(end, 3),
            "decision": label,
            "role": str(decision.get("role") or ""),
            "reason": str(decision.get("reason") or ""),
            "order_index": source_video_id * 100000 + index,
        },
        None,
    )


def _merge_quality_decisions(decisions: list[dict]) -> list[dict]:
    ordered = sorted(decisions, key=lambda item: (int(item["source_video_id"]), float(item["start"]), float(item["end"])))
    merged: list[dict] = []
    for item in ordered:
        current = dict(item)
        if not merged:
            merged.append(current)
            continue
        previous = merged[-1]
        same_source = int(previous["source_video_id"]) == int(current["source_video_id"])
        same_decision = previous.get("decision") == current.get("decision")
        close_or_overlap = float(current["start"]) <= float(previous["end"]) + 0.35
        if same_source and same_decision and close_or_overlap:
            previous["end"] = round(max(float(previous["end"]), float(current["end"])), 3)
            previous["reason"] = _join_unique_text(previous.get("reason", ""), current.get("reason", ""))
            previous["role"] = _join_unique_text(previous.get("role", ""), current.get("role", ""), separator=",")
            continue
        merged.append(current)
    for index, item in enumerate(merged, start=1):
        item["order_index"] = index
    return merged


def _improve_quality_decisions(decisions: list[dict], keep_policy: str) -> tuple[list[dict], list[dict]]:
    adjustments: list[dict] = []
    min_keep_seconds = 1.5 if keep_policy == "strict" else 1.0
    bridge_gap_seconds = 1.2 if keep_policy == "strict" else 2.5
    filtered = []
    for item in decisions:
        duration = float(item["end"]) - float(item["start"])
        if item.get("decision") in {"keep_required", "keep_optional"} and duration < min_keep_seconds:
            adjustments.append(
                {
                    "type": "drop_short_keep",
                    "source_video_id": item.get("source_video_id"),
                    "start": item.get("start"),
                    "end": item.get("end"),
                    "reason": f"保留段短于 {min_keep_seconds:.1f} 秒，容易造成跳切。",
                }
            )
            continue
        filtered.append(item)

    merged: list[dict] = []
    for item in filtered:
        current = dict(item)
        if not merged:
            merged.append(current)
            continue
        previous = merged[-1]
        same_source = int(previous["source_video_id"]) == int(current["source_video_id"])
        previous_keep = previous.get("decision") in {"keep_required", "keep_optional"}
        current_keep = current.get("decision") in {"keep_required", "keep_optional"}
        gap = float(current["start"]) - float(previous["end"])
        if same_source and previous_keep and current_keep and 0 <= gap <= bridge_gap_seconds:
            previous["end"] = current["end"]
            previous["decision"] = _stronger_keep_label(previous.get("decision"), current.get("decision"))
            previous["reason"] = _join_unique_text(previous.get("reason", ""), current.get("reason", ""))
            previous["role"] = _join_unique_text(previous.get("role", ""), current.get("role", ""), separator=",")
            adjustments.append(
                {
                    "type": "bridge_short_gap",
                    "source_video_id": current.get("source_video_id"),
                    "start": previous.get("start"),
                    "end": current.get("end"),
                    "gap_seconds": round(gap, 3),
                    "reason": "相邻保留段间隔很短，合并以降低跳切和断句风险。",
                }
            )
            continue
        merged.append(current)

    for index, item in enumerate(merged, start=1):
        item["order_index"] = index
    return merged, adjustments


def _stronger_keep_label(left: str | None, right: str | None) -> str:
    if "keep_required" in {left, right}:
        return "keep_required"
    return "keep_optional"


def _kept_quality_decisions(decisions: list[dict], keep_policy: str) -> list[dict]:
    if keep_policy == "strict":
        labels = {"keep_required"}
    elif keep_policy == "loose":
        labels = {"keep_required", "keep_optional"}
    else:
        labels = {"keep_required", "keep_optional"}
    return [item for item in decisions if item.get("decision") in labels]


def _quality_source_summaries(videos: list[dict], decisions: list[dict], kept: list[dict]) -> list[dict]:
    summaries = []
    for video in videos:
        source_id = int(video["id"])
        duration = float(video.get("duration") or 0)
        source_decisions = [item for item in decisions if int(item.get("source_video_id") or 0) == source_id]
        source_kept = [item for item in kept if int(item.get("source_video_id") or 0) == source_id]
        kept_seconds = sum(float(item["end"]) - float(item["start"]) for item in source_kept)
        summaries.append(
            {
                "source_video_id": source_id,
                "source_video_name": video.get("name") or "",
                "duration": round(duration, 3),
                "decision_count": len(source_decisions),
                "kept_count": len(source_kept),
                "kept_seconds": round(kept_seconds, 3),
                "kept_ratio": round(kept_seconds / duration, 4) if duration > 0 else 0,
            }
        )
    return summaries


def _quality_risks(source_summaries: list[dict], rejected: list[dict], review: dict) -> list[str]:
    risks = []
    for summary in source_summaries:
        if summary["kept_count"] == 0:
            risks.append(f"{summary['source_video_name']} 没有保留片段。")
        elif summary["duration"] > 0 and summary["kept_ratio"] < 0.08:
            risks.append(f"{summary['source_video_name']} 保留比例低于 8%，可能漏掉剧情。")
        elif summary["duration"] > 0 and summary["kept_ratio"] > 0.92:
            risks.append(f"{summary['source_video_name']} 保留比例高于 92%，精剪效果可能不明显。")
    if rejected:
        risks.append(f"有 {len(rejected)} 条模型决策被校验拒绝。")
    for risk in review.get("risks") or []:
        text = str(risk).strip()
        if text:
            risks.append(text)
    return risks


def _join_unique_text(left: str, right: str, separator: str = " | ") -> str:
    values = []
    for value in [left, right]:
        text = str(value or "").strip()
        if text and text not in values:
            values.append(text)
    return separator.join(values)


def _bounded_int(value: object, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _get_project_video(project_id: int, video_id: int) -> dict:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM videos WHERE id = ? AND project_id = ?",
            (video_id, project_id),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="video not found in project")
    return dict(row)


def _get_project(project_id: int) -> dict:
    with connect() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="project not found")
    return dict(row)


def _get_run_source_videos(project_id: int, run_id: int) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT v.*
            FROM pipeline_run_sources s
            JOIN videos v ON v.id = s.source_video_id
            WHERE s.run_id = ? AND s.project_id = ? AND v.project_id = ?
            ORDER BY s.order_index, s.id
            """,
            (run_id, project_id, project_id),
        ).fetchall()
    return rows_to_dicts(rows)


def _dedupe_ids(ids: list[int]) -> list[int]:
    seen = set()
    result = []
    for item in ids:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _mark_step_running(step_id: int, context: dict) -> None:
    context["current_step_id"] = step_id
    with connect() as conn:
        conn.execute(
            """
            UPDATE pipeline_steps
            SET status = 'running',
                progress = 10,
                input_json = ?,
                output_json = '',
                error = '',
                started_at = CURRENT_TIMESTAMP,
                finished_at = NULL
            WHERE id = ?
            """,
            (json.dumps({"params": context.get("params"), "artifacts": list(context.get("artifacts", {}).keys())}, ensure_ascii=False), step_id),
        )


def _mark_step_succeeded(step_id: int, output: dict) -> None:
    with connect() as conn:
        conn.execute(
            """
            UPDATE pipeline_steps
            SET status = 'succeeded',
                progress = 100,
                output_json = ?,
                finished_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (json.dumps(output, ensure_ascii=False, default=str), step_id),
        )


def _update_run_progress(run_id: int, current_step: str, progress: int) -> None:
    with connect() as conn:
        conn.execute(
            """
            UPDATE pipeline_runs
            SET current_step = ?,
                progress = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (current_step, progress, run_id),
        )


def _record_artifact(context: dict, step_id: int, artifact_type: str, title: str, content: dict) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO artifacts
                (project_id, source_video_id, pipeline_run_id, pipeline_step_id, type, title, content_json, metadata_json, is_final)
            VALUES
                (?, ?, ?, ?, ?, ?, ?, '{}', 0)
            """,
            (
                context["project_id"],
                context["video"]["id"],
                context["run_id"],
                step_id,
                artifact_type,
                title,
                json.dumps(content, ensure_ascii=False, default=str),
            ),
        )


def _normalize_run(row: dict) -> dict:
    return {
        **row,
        "params": _loads(row.get("params_json")),
        "prompt_snapshot": _loads(row.get("prompt_snapshot_json")),
        "result": _loads(row.get("result_json")),
    }


def _normalize_step(row: dict) -> dict:
    return {
        **row,
        "input": _loads(row.get("input_json")),
        "output": _loads(row.get("output_json")),
    }


def _normalize_artifact(row: dict) -> dict:
    return {
        **row,
        "content": _loads(row.get("content_json")),
        "metadata": _loads(row.get("metadata_json")),
        "is_final": bool(row.get("is_final")),
    }


def _normalize_asset(row: dict) -> dict:
    return {
        **row,
        "metadata": _loads(row.get("metadata_json")),
    }


def _normalize_job(row: dict) -> dict:
    return dict(row)


def _ensure_pipeline_run(run_id: int, project_id: int | None = None) -> dict:
    with connect() as conn:
        if project_id is None:
            row = conn.execute("SELECT * FROM pipeline_runs WHERE id = ?", (run_id,)).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM pipeline_runs WHERE id = ? AND project_id = ?",
                (run_id, project_id),
            ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="pipeline run not found")
    return dict(row)


def _snapshot_prompt_configs(prompt_config_ids: list[int]) -> dict:
    with connect() as conn:
        if prompt_config_ids:
            placeholders = ",".join("?" for _ in prompt_config_ids)
            rows = conn.execute(
                f"SELECT * FROM prompt_configs WHERE id IN ({placeholders}) ORDER BY id",
                prompt_config_ids,
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM prompt_configs WHERE category = 'video_generation' AND enabled = 1 ORDER BY id"
            ).fetchall()
    prompts = rows_to_dicts(rows)
    return {
        "prompts": [
            {
                "id": item["id"],
                "key": item["key"],
                "name": item["name"],
                "category": item["category"],
                "content": item["content"],
                "enabled": bool(item["enabled"]),
                "is_system": bool(item["is_system"]),
            }
            for item in prompts
        ]
    }


def _loads(value: str | None) -> dict:
    try:
        return json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}


def _prompt_snapshot_text(prompt_snapshot: dict, key: str) -> str:
    for item in prompt_snapshot.get("prompts") or []:
        if item.get("key") == key and item.get("enabled", True):
            return str(item.get("content") or "")
    return ""
