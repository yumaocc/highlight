import base64
import json
import shutil
import subprocess
import time
import wave
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import httpx

from .config import get_settings
from .prompts import get_prompt_text


class AIClientError(RuntimeError):
    pass


def _post_with_retry(
    url: str,
    headers: dict,
    json_payload: Optional[dict] = None,
    data: Optional[dict] = None,
    files: Optional[dict] = None,
    timeout: int = 120,
    attempts: int = 3,
) -> httpx.Response:
    last_exc: Optional[Exception] = None
    for attempt in range(1, attempts + 1):
        try:
            response = httpx.post(
                url,
                headers=headers,
                json=json_payload,
                data=data,
                files=files,
                timeout=timeout,
            )
            if response.status_code in {408, 429, 500, 502, 503, 504, 524} and attempt < attempts:
                time.sleep(1.2 * attempt)
                continue
            return response
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            last_exc = exc
            if attempt < attempts:
                time.sleep(0.8 * attempt)
                continue
            raise
    if last_exc:
        raise last_exc
    raise AIClientError("request failed without response")


def generate_short_drama_template_visual(
    kind: str,
    drama_name: str,
    style: str,
    brief: str,
    duration: int,
    output_path: Path,
    reference_image_path: Optional[Path] = None,
    gemini_strategy: Optional[dict] = None,
    image_model: Optional[str] = None,
    timeout_seconds: int = 300,
    attempts: int = 3,
    compact_prompt: bool = False,
) -> dict:
    settings = get_settings()
    if not settings.openai_api_key:
        return {"ok": False, "error": "OPENAI_API_KEY is not configured"}

    prompt = (
        build_compact_short_drama_visual_prompt(kind, drama_name, style, brief)
        if compact_prompt
        else build_short_drama_template_visual_prompt(
            kind=kind,
            drama_name=drama_name,
            style=style,
            brief=brief,
            duration=duration,
            gemini_strategy=gemini_strategy,
        )
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path = output_path.with_suffix(".prompt.md")
    prompt_path.write_text(f"{prompt.rstrip()}\n", encoding="utf-8")

    try:
        if reference_image_path and reference_image_path.exists():
            response = _openai_image_edit(
                prompt,
                output_path,
                reference_image_path,
                image_model=image_model,
                timeout_seconds=timeout_seconds,
                attempts=attempts,
            )
            mode = "edit"
        else:
            response = _openai_image_generation(
                prompt,
                output_path,
                image_model=image_model,
                timeout_seconds=timeout_seconds,
                attempts=attempts,
            )
            mode = "generation"
        model = image_model or settings.openai_image_model
        return {
            "ok": True,
            "kind": kind,
            "mode": mode,
            "model": model,
            "prompt": prompt,
            "prompt_path": str(prompt_path),
            "output_path": str(output_path),
            "gemini_strategy": gemini_strategy or {},
            "raw": response,
        }
    except Exception as exc:  # noqa: BLE001 - surface image gateway failures to UI.
        return {
            "ok": False,
            "kind": kind,
            "model": image_model or settings.openai_image_model,
            "prompt": prompt,
            "prompt_path": str(prompt_path),
            "gemini_strategy": gemini_strategy or {},
            "error": str(exc),
        }


def gemini_plan_short_drama_template_visual(
    kind: str,
    drama_name: str,
    style: str,
    brief: str,
    duration: int,
) -> dict:
    settings = get_settings()
    if not settings.gemini_api_key:
        return {"ok": False, "error": "GEMINI_API_KEY is not configured"}
    role = "片头" if kind == "intro" else "片尾"
    prompt = {
        "task": f"为短剧竖屏{role}模板做视觉策略，不直接生成图片。",
        "drama_name": drama_name,
        "style": style,
        "brief": _compress_visual_brief(brief),
        "duration_seconds": duration,
        "platform": "抖音/快手/小红书竖屏短视频",
        "decision_rules": [
            "先判断这个模板应该用什么冲突瞬间作为画面主体。",
            "片头负责快速抓人，片尾负责悬念和继续观看动机。",
            "输出要能指导 GPT Image 生成高点击短剧视觉图。",
            "同时给出后续转成 2-3 秒视频时的运动建议。",
        ],
        "return_json": {
            "visual_concept": "中文，一句话视觉主概念",
            "main_subject": "主体人物/场景",
            "hook_copy": "不超过 10 个中文字符",
            "composition": "构图建议",
            "motion_plan": "转成短视频片头片尾时的推拉/闪白/缩放建议",
            "risk_checks": ["需要避免的问题"],
            "prompt_additions": ["应该加入 GPT 图像 prompt 的要点"],
        },
    }
    result = _gemini_text_json(settings.gemini_model, prompt)
    if result.get("ok"):
        result["provider"] = "gemini"
        result["model"] = settings.gemini_model
    return result


def build_short_drama_template_visual_prompt(
    kind: str,
    drama_name: str,
    style: str,
    brief: str,
    duration: int,
    gemini_strategy: Optional[dict] = None,
) -> str:
    role = "片头" if kind == "intro" else "片尾"
    headline = drama_name.strip() or "短剧高能片段"
    mood = style.strip() or "强冲突快节奏"
    if kind == "intro":
        copy_line = ""
        main_title = headline
        text_rule = "片头尽量少字；如果需要中文文字，只允许使用真实剧名/素材名，不要副标题、营销词、制作词或流程说明词。"
        outro_rule = "片头要在第一眼制造剧情冲突感，不要像制作说明页。"
    else:
        main_title = "点击左下角"
        copy_line = "观看全集"
        text_rule = "片尾中文必须围绕“点击左下角”“观看全集”，不要写给剪辑师看的说明。"
        outro_rule = "片尾要留悬念和继续观看动机，不要像广告落版。"
    user_brief = _compress_visual_brief(brief)
    reference_rule = (
        "如果提供参考图，必须以参考图中的人物、服装、场景氛围和短剧质感为基础进行影视化增强，"
        "不要生成与参考剧情无关的通用海报。"
    )
    payload = {
        "type": "短剧短视频片头/片尾视觉图",
        "goal": f"生成一张可作为 {duration} 秒短剧{role}动画底图的竖版视觉图",
        "platform": "抖音 / 快手 / 小红书竖屏短视频",
        "aspect_ratio": "9:16",
        "drama": {
            "name": headline,
            "visual_role": role,
            "style": mood,
            "story_visual_hint": user_brief,
        },
        "layout": {
            "main_title": main_title,
            "hook_line": copy_line,
            "title_priority": "大标题一眼可读，但不要遮住人物脸部或核心画面",
            "safe_areas": "顶部和底部保留安全边距，方便后续加字幕、进度条或平台 UI",
            "text_rule": text_rule,
        },
        "visual_direction": {
            "scene": f"围绕“{user_brief}”做短剧冲突瞬间的电影感海报，不要出现真实平台水印",
            "composition": "强主体，强情绪，背景有层次，适合做轻微推拉动画",
            "lighting": "戏剧化但清晰，人物轮廓明确，高对比，移动端小屏可读",
            "reference_image_rule": reference_rule,
        },
        "multi_model_decision": {
            "gemini_strategy": _compact_template_decision(gemini_strategy or {}),
            "gpt_role": "根据 Gemini 的视觉策略生成最终竖版视觉图",
        },
        "style_rules": {
            "must_feel": "像真实短剧平台上高点击率的片头/片尾视觉，不是普通静态海报",
            "typography": "中文大字准确、少字、醒目，避免长句",
            "color": "高对比但不脏，避免廉价饱和渐变堆叠",
            "extra_rule": outro_rule,
        },
        "constraints": {
            "must_keep": [
                "竖版 9:16",
                "贴合参考图和短剧剧情内容",
                "画面中心留出可动画化主体",
                "中文文字尽量少且可读",
                "不出现平台 logo、水印、二维码",
            ],
            "avoid": [
                "文字错别字",
                "过度拥挤",
                "多平台 UI 混杂",
                "血腥暴力或低俗元素",
                "任何营销副标题",
                "任何制作方式说明",
                "任何内容筛选说明",
                "任何回顾提示语",
                "内部制作词",
                "流程说明词",
                "审看说明词",
                "制作说明词",
            ],
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def build_compact_short_drama_visual_prompt(kind: str, drama_name: str, style: str, brief: str) -> str:
    title = drama_name.strip() or "短剧高能片段"
    story = _compress_visual_brief(brief)
    if kind == "intro":
        copy_rule = f"Only include this Chinese title if text is needed: {title}. No other text."
        goal = "a cinematic opening cover with one immediate dramatic conflict"
    else:
        copy_rule = 'The only Chinese text allowed is: "点击左下角" and "观看全集".'
        goal = "a suspenseful ending cover with a clear visual cue toward the lower-left corner"
    return (
        f"Create a polished 9:16 vertical short-drama poster for {goal}. "
        f"Story: {story}. Visual style: {style or 'cinematic, realistic, high contrast'}. "
        "Use one strong subject, realistic faces, dramatic but clean lighting, layered background, "
        "clear mobile composition, and safe margins. Do not make a collage. "
        f"{copy_rule} No platform UI, logo, watermark, QR code, production notes, or marketing subtitle."
    )


def generate_promotion_content(description: str, audience: str, tone: str, platform: str) -> dict:
    prompt = {
        "role": "你是一位有十年以上实战经验的资深内容推广大师，擅长把普通描述转化为可信、有传播力的社交媒体内容。",
        "task": "基于用户描述完善一套可以直接发布的推广内容，并为宣传图提供精简英文视觉提示词。",
        "user_description": description[:6000],
        "target_audience": audience,
        "tone": tone,
        "target_platform": platform,
        "requirements": [
            "保持事实边界，不虚构价格、数据、资质、用户评价或承诺。",
            "标题简洁有吸引力，建议不超过20个中文字符。",
            "正文先给核心价值，再补充具体亮点和明确行动建议，避免空洞口号。",
            "话题标签提供3到8个，不要包含#符号。",
            "image_prompt必须是适合GPT Image 2的精简英文提示词，描述主体、场景、构图、光线、色彩与禁用项。",
            "宣传图不要生成大段文字、平台UI、logo、水印或二维码。",
        ],
        "return_json": {
            "title": "中文推广标题",
            "content": "中文推广正文",
            "topics": ["话题1", "话题2"],
            "image_prompt": "Concise English image-generation prompt",
            "strategy": "一句话说明推广策略",
        },
    }
    result = _openai_json(prompt)
    if not result.get("ok"):
        return result
    result["title"] = str(result.get("title") or "").strip()
    result["content"] = str(result.get("content") or "").strip()
    result["topics"] = [str(item).strip().lstrip("#") for item in result.get("topics") or [] if str(item).strip()][:8]
    result["image_prompt"] = str(result.get("image_prompt") or "").strip()
    if not result["title"] or not result["content"] or not result["image_prompt"]:
        return {"ok": False, "error": "推广内容模型返回字段不完整", "raw": result}
    return result


def generate_image_from_prompt(
    prompt: str,
    output_path: Path,
    *,
    image_model: Optional[str] = None,
    timeout_seconds: int = 180,
    attempts: int = 2,
) -> dict:
    settings = get_settings()
    if not settings.openai_api_key:
        return {"ok": False, "error": "OPENAI_API_KEY is not configured"}
    final_prompt = " ".join(prompt.split())
    output_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path = output_path.with_suffix(".prompt.md")
    prompt_path.write_text(f"{final_prompt}\n", encoding="utf-8")
    try:
        response = _openai_image_generation(
            final_prompt,
            output_path,
            image_model=image_model,
            timeout_seconds=timeout_seconds,
            attempts=attempts,
        )
        return {
            "ok": True,
            "mode": "generation",
            "model": image_model or settings.openai_image_model,
            "prompt": final_prompt,
            "prompt_path": str(prompt_path),
            "output_path": str(output_path),
            "raw": response,
        }
    except Exception as exc:  # noqa: BLE001 - return a structured gateway error.
        return {
            "ok": False,
            "model": image_model or settings.openai_image_model,
            "prompt": final_prompt,
            "prompt_path": str(prompt_path),
            "error": str(exc),
        }


def _compact_template_decision(value: dict) -> dict:
    if not value:
        return {}
    allowed = {
        "ok",
        "provider",
        "model",
        "visual_concept",
        "main_subject",
        "hook_copy",
        "composition",
        "motion_plan",
        "risk_checks",
        "prompt_additions",
        "decision",
        "reason",
        "recommended_prompt_additions",
        "animation_plan",
        "error",
    }
    return {key: value for key, value in value.items() if key in allowed}


def _compress_visual_brief(brief: str) -> str:
    text = " ".join((brief or "").replace("\r", "\n").split())
    if not text:
        return "短剧主角逆袭、高能冲突、命运转折"

    keyword_groups = [
        ("篮球三分逆袭", ["篮球", "三分", "投篮", "绝杀", "联赛", "队友", "教练", "球探"]),
        ("轮椅绝杀奇迹", ["轮椅", "重伤", "跟腱", "0.4 秒", "绝杀"]),
        ("足球跨界封神", ["足球", "世界杯", "射门", "国家队", "逆转"]),
        ("百米田径新篇章", ["百米", "田径", "世界纪录"]),
        ("被轻视后开挂翻盘", ["轻视", "嘲讽", "系统", "逆袭", "封神"]),
        ("甜宠情感线", ["美女教练", "林教练", "恋爱", "爱慕"]),
    ]
    selected = [label for label, keys in keyword_groups if any(key in text for key in keys)]
    if selected:
        return "，".join(selected[:4])

    short = text[:260]
    pivot = max(short.rfind("。"), short.rfind("，"), short.rfind("."))
    if pivot >= 40:
        short = short[:pivot]
    return short[:260]


def _openai_image_generation(
    prompt: str,
    output_path: Path,
    *,
    image_model: Optional[str] = None,
    timeout_seconds: int = 300,
    attempts: int = 3,
) -> dict:
    settings = get_settings()
    base_url = _openai_v1_base(settings.openai_base_url)
    payload = {
        "model": image_model or settings.openai_image_model,
        "prompt": prompt,
        "size": "1024x1536",
        "quality": "auto",
        "n": 1,
    }
    response = _post_with_retry(
        f"{base_url}/images/generations",
        headers={"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"},
        json_payload=payload,
        timeout=max(1, int(timeout_seconds)),
        attempts=max(1, int(attempts)),
    )
    response.raise_for_status()
    payload = response.json()
    _save_openai_image_response(payload, output_path)
    return _compact_image_response(payload)


def _openai_image_edit(
    prompt: str,
    output_path: Path,
    reference_image_path: Path,
    *,
    image_model: Optional[str] = None,
    timeout_seconds: int = 300,
    attempts: int = 3,
) -> dict:
    settings = get_settings()
    base_url = _openai_v1_base(settings.openai_base_url)
    with reference_image_path.open("rb") as handle:
        files = {
            "image": (reference_image_path.name, handle, _image_mime(reference_image_path)),
        }
        data = {
            "model": image_model or settings.openai_image_model,
            "prompt": prompt,
            "size": "1024x1536",
            "quality": "auto",
            "n": "1",
        }
        response = _post_with_retry(
            f"{base_url}/images/edits",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            data=data,
            files=files,
            timeout=max(1, int(timeout_seconds)),
            attempts=max(1, int(attempts)),
        )
    response.raise_for_status()
    payload = response.json()
    _save_openai_image_response(payload, output_path)
    return _compact_image_response(payload)


def _save_openai_image_response(payload: dict, output_path: Path) -> None:
    first = (payload.get("data") or [None])[0] or {}
    if first.get("b64_json"):
        output_path.write_bytes(base64.b64decode(first["b64_json"]))
        return
    if first.get("url"):
        with httpx.stream("GET", first["url"], timeout=120) as response:
            response.raise_for_status()
            with output_path.open("wb") as handle:
                for chunk in response.iter_bytes():
                    handle.write(chunk)
        return
    raise AIClientError("Image API response did not include b64_json or url")


def _compact_image_response(payload: dict) -> dict:
    compact = {key: value for key, value in payload.items() if key != "data"}
    data = payload.get("data") or []
    compact["data"] = [
        {
            key: ("<base64 omitted>" if key == "b64_json" else value)
            for key, value in item.items()
        }
        for item in data
    ]
    return compact


def image_task_filename(kind: str, drama_name: str) -> str:
    safe_name = "".join(ch if ch.isalnum() else "_" for ch in drama_name.strip())[:60] or "short_drama"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{safe_name}_{kind}_{stamp}.png"


def openai_transcribe_audio(audio_path: Path) -> dict:
    settings = get_settings()
    if not settings.openai_api_key:
        return {"ok": False, "text": "", "error": "OPENAI_API_KEY is not configured"}

    base_url = _api_base(settings.openai_base_url, "https://api.openai.com")
    url = f"{base_url}/v1/audio/transcriptions"
    headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
    with audio_path.open("rb") as handle:
        files = {"file": (audio_path.name, handle, "audio/mpeg")}
        data = {
            "model": settings.openai_transcribe_model,
            "response_format": "json",
        }
        try:
            response = _post_with_retry(url, headers=headers, data=data, files=files, timeout=120)
            response.raise_for_status()
        except Exception as exc:  # noqa: BLE001 - batch pipeline records API failures per clip.
            return {"ok": False, "text": "", "error": str(exc)}
    payload = response.json()
    return {"ok": True, "text": payload.get("text", ""), "raw": payload}


def transcribe_audio(audio_path: Path) -> dict:
    settings = get_settings()
    if settings.transcribe_provider.lower() == "openai":
        return openai_transcribe_audio(audio_path)
    return gemini_transcribe_audio(audio_path)


def gemini_transcribe_audio(audio_path: Path) -> dict:
    settings = get_settings()
    if not settings.gemini_api_key:
        return {"ok": False, "text": "", "error": "GEMINI_API_KEY is not configured"}
    base_url = _api_base(
        settings.google_gemini_base_url or settings.gemini_base_url,
        "https://generativelanguage.googleapis.com",
    )
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": get_prompt_text("transcribe_audio")
                    },
                    {
                        "inline_data": {
                            "mime_type": _audio_mime(audio_path),
                            "data": _read_b64(audio_path),
                        }
                    },
                ],
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json",
        },
    }
    try:
        response = _post_with_retry(
            f"{base_url}/v1beta/models/{settings.gemini_model}:generateContent",
            headers={"x-goog-api-key": settings.gemini_api_key, "Content-Type": "application/json"},
            json_payload=payload,
            timeout=120,
        )
        response.raise_for_status()
        text = _extract_gemini_text(response.json())
        parsed = _parse_json_content(text)
        transcript = parsed.get("transcript") or parsed.get("text") or ""
        return {"ok": bool(parsed.get("ok", True)) and bool(transcript), "text": transcript, "raw": parsed}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "text": "", "error": str(exc)}


def gemini_generate_tts_wav(text: str, output_path: Path, style: str = "") -> dict:
    settings = get_settings()
    if not settings.gemini_api_key:
        return {"ok": False, "error": "GEMINI_API_KEY is not configured"}
    if not text.strip():
        return {"ok": False, "error": "empty tts text"}
    base_url = _api_base(
        settings.google_gemini_base_url or settings.gemini_base_url,
        "https://generativelanguage.googleapis.com",
    )
    prompt = (
        f"{style.strip()}：{text.strip()}"
        if style.strip()
        else text.strip()
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {
                        "voiceName": settings.gemini_tts_voice,
                    }
                }
            },
        },
        "model": settings.gemini_tts_model,
    }
    try:
        response = _post_with_retry(
            f"{base_url}/v1beta/models/{settings.gemini_tts_model}:generateContent",
            headers={"x-goog-api-key": settings.gemini_api_key, "Content-Type": "application/json"},
            json_payload=payload,
            timeout=120,
        )
        response.raise_for_status()
        payload = response.json()
        audio_data = _extract_gemini_audio_b64(payload)
        if not audio_data:
            return {"ok": False, "error": "Gemini TTS response did not include audio data", "raw": payload}
        pcm = base64.b64decode(audio_data)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        _write_pcm_wav(output_path, pcm, sample_rate=24000, channels=1, sample_width=2)
        return {
            "ok": True,
            "text": text.strip(),
            "output_path": str(output_path),
            "model": settings.gemini_tts_model,
            "voice": settings.gemini_tts_voice,
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "text": text.strip(), "error": str(exc)}


def generate_voiceover_wav(text: str, output_path: Path, style: str = "") -> dict:
    gemini_result = gemini_generate_tts_wav(text, output_path, style=style)
    if gemini_result.get("ok"):
        gemini_result["provider"] = "gemini"
        return gemini_result
    local_result = local_say_tts_wav(text, output_path)
    if local_result.get("ok"):
        local_result["provider"] = "macos_say"
        local_result["fallback_from"] = {"provider": "gemini", "error": gemini_result.get("error")}
        return local_result
    return {
        "ok": False,
        "text": text.strip(),
        "error": "Gemini TTS failed and local say fallback failed",
        "gemini_error": gemini_result.get("error"),
        "local_error": local_result.get("error"),
    }


def local_say_tts_wav(text: str, output_path: Path) -> dict:
    say_path = shutil.which("say")
    if not say_path:
        return {"ok": False, "text": text.strip(), "error": "macOS say command not found"}
    aiff_path = output_path.with_suffix(".aiff")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [say_path, "-v", "Tingting", "-r", "210", "-o", str(aiff_path), text.strip()],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(aiff_path),
                "-ar",
                "44100",
                "-ac",
                "2",
                str(output_path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        return {"ok": True, "text": text.strip(), "output_path": str(output_path)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "text": text.strip(), "error": str(exc)}
    finally:
        aiff_path.unlink(missing_ok=True)


def openai_analyze_transcript(transcript: str, start_seconds: float, end_seconds: float) -> dict:
    if not transcript.strip():
        return {"ok": False, "score": 0.0, "summary": "", "error": "empty transcript"}
    prompt = {
        "task": "Analyze a short-drama clip transcript for highlight value.",
        "operator_prompt": get_prompt_text("highlight_transcript_review"),
        "time_range_seconds": [start_seconds, end_seconds],
        "transcript": transcript[:6000],
        "scoring_rules": [
            "Conflict, reveal, emotional outburst, hook line, cliffhanger.",
            "Prefer narrative continuity over isolated loud moments.",
        ],
        "return_json": {
            "score": "0-1",
            "summary": "one sentence",
            "hook": "best hook line if any",
            "continuity": "whether the clip starts and ends coherently",
        },
    }
    settings = get_settings()
    content = (
        "Return concise valid JSON only.\n"
        + json.dumps(prompt, ensure_ascii=False)
    )
    if settings.openai_wire_api.lower() == "responses":
        return _responses_json(settings.openai_text_model, content)
    return _chat_json(
        provider="openai",
        model=settings.openai_text_model,
        messages=[
            {"role": "system", "content": "Return concise valid JSON only."},
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
    )


def openai_classify_promo_segment(
    transcript: str,
    visual_summary: str,
    start_seconds: float,
    end_seconds: float,
) -> dict:
    prompt = {
        "task": "Classify a short-drama segment for a promotional trailer, not a raw highlight clip.",
        "operator_prompt": get_prompt_text("promo_segment_classification"),
        "time_range_seconds": [start_seconds, end_seconds],
        "transcript": transcript[:5000],
        "visual_summary": visual_summary[:2000],
        "roles": ["hook", "setup", "relationship", "conflict", "reveal", "emotional_peak", "cliffhanger", "skip"],
        "selection_goal": "Build a 30-60 second promo that quickly introduces the story, characters, conflict, and leaves a reason to watch full episodes.",
        "return_json": {
            "role": "one role from roles",
            "promo_score": "0-1",
            "reason": "why this helps a promo",
            "voiceover": "one short Chinese line that could introduce this beat",
            "title_hook": "short Chinese hook if useful",
            "opening_text": "very short Chinese on-screen hook if this can open the promo",
            "ending_text": "very short Chinese cliffhanger/CTA if this can close the promo",
            "opening_strength": "0-1 score for first 3 seconds hook potential",
            "cliffhanger_strength": "0-1 score for ending curiosity potential",
        },
    }
    content = "Return concise valid JSON only.\n" + json.dumps(prompt, ensure_ascii=False)
    settings = get_settings()
    if settings.openai_wire_api.lower() == "responses":
        return _responses_json(settings.openai_text_model, content)
    return _chat_json(
        provider="openai",
        model=settings.openai_text_model,
        messages=[
            {"role": "system", "content": "Return concise valid JSON only."},
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
    )


def openai_draft_promo_edit(candidates: list[dict], target_seconds: float = 90.0) -> dict:
    if not candidates:
        return {"ok": False, "error": "no candidates"}
    prompt = {
        "task": "Create a short-drama promotional edit plan from candidate scenes.",
        "operator_prompt": get_prompt_text("promo_edit_draft"),
        "target_seconds": target_seconds,
        "candidates": _compact_promo_candidates(candidates),
        "editing_rules": [
            "The output is a promo that makes viewers want to watch the full drama, not a random highlight reel.",
            "Choose 3-4 candidate scenes in chronological story order.",
            "Continuity is more important than maximum score: avoid cuts that interrupt a person before they speak or before the reaction finishes.",
            "Prefer scenes that introduce character relationship, then conflict, then reveal or cliffhanger.",
            "If a high-score candidate feels like the middle of a sentence, use a lower-score but more complete candidate.",
        ],
        "return_json": {
            "selected_candidate_ids": ["candidate id numbers in final order"],
            "storyline": "one Chinese sentence describing the edit's story arc",
            "continuity_notes": "Chinese notes about why these cuts feel coherent",
            "opening_text": "short Chinese title, 10 Chinese characters or fewer if possible",
            "ending_text": "short Chinese cliffhanger/CTA",
        },
    }
    return _openai_json(prompt)


def gemini_review_promo_edit(candidates: list[dict], draft: dict, target_seconds: float = 90.0) -> dict:
    if not candidates:
        return {"ok": False, "error": "no candidates"}
    prompt = {
        "task": "Review GPT's short-drama promotional edit plan for continuity and viewer attraction.",
        "operator_prompt": get_prompt_text("promo_edit_review"),
        "target_seconds": target_seconds,
        "candidates": _compact_promo_candidates(candidates),
        "gpt_draft": draft,
        "review_rules": [
            "Act as the continuity editor.",
            "Flag any selected scene that looks like it starts too late, ends too early, interrupts dialogue, or jumps before a reaction.",
            "Suggest replacements only from the candidate ids provided.",
            "Keep the final story easy to understand for a first-time viewer.",
        ],
        "return_json": {
            "accepted": "true|false",
            "suggested_candidate_ids": ["candidate id numbers in suggested final order"],
            "continuity_risks": ["Chinese list of risks"],
            "reason": "Chinese review summary",
            "opening_text": "optional improved short title",
            "ending_text": "optional improved cliffhanger/CTA",
        },
    }
    settings = get_settings()
    if not settings.gemini_api_key:
        return {"ok": False, "error": "GEMINI_API_KEY is not configured"}
    return _gemini_text_json(settings.gemini_model, prompt)


def gemini_watch_story_quality_proxies(
    proxy_videos: list[dict],
    keep_policy: str = "balanced",
    operator_prompt: str = "",
) -> dict:
    settings = get_settings()
    if not settings.gemini_api_key:
        return {"ok": False, "error": "GEMINI_API_KEY is not configured"}
    if not proxy_videos:
        return {"ok": False, "error": "no proxy videos"}
    prompt = {
        "task": "Watch compressed proxy videos from a short drama and produce a quality cut plan.",
        "operator_prompt": operator_prompt or get_prompt_text("story_quality_cut_review"),
        "keep_policy": keep_policy,
        "source_videos": [
            {
                "source_video_id": item.get("source_video_id"),
                "source_video_name": item.get("source_video_name"),
                "order_index": item.get("order_index"),
                "duration_seconds": item.get("proxy_duration") or item.get("source_duration"),
            }
            for item in proxy_videos
        ],
        "editing_goal": [
            "This is not a promo trailer.",
            "Do not target a fixed duration.",
            "Keep useful story material that preserves continuity, character relationship, conflict setup, reversals, emotional beats, and cliffhangers.",
            "Drop repeated, low-information, unclear, dead-air, redundant, or non-progressing footage.",
            "Identify and drop source-video built-in outros/end cards, including 未完待续, 下集更精彩, 关注/点赞/收藏, 点击左下角看全集, 看全集, platform CTA slates, duplicate promo cards, black/frozen ending screens, credits, and end titles.",
            "Do not keep a source outro just because it has music, text, or strong CTA. If the end area contains real story information, keep only the story-relevant part and drop the outro/end-card part.",
            "Keep chronological order unless an item is explicitly marked drop.",
        ],
        "decision_labels": {
            "keep_required": "must keep for story understanding or payoff",
            "keep_optional": "useful reaction, mood, transition, or context",
            "drop": "low-value material that can be removed",
        },
        "return_json": {
            "summary": "Chinese summary of the quality cut strategy",
            "decisions": [
                {
                    "source_video_id": "integer from source_videos",
                    "source_video_name": "string",
                    "start": "seconds on that source/proxy timeline",
                    "end": "seconds on that source/proxy timeline",
                    "decision": "keep_required|keep_optional|drop",
                    "role": "setup|relationship|conflict|reveal|reaction|transition|cliffhanger|source_outro|low_value",
                    "reason": "Chinese reason",
                }
            ],
            "quality_notes": "Chinese notes about pacing and continuity",
            "risks": ["Chinese list of uncertainties"],
        },
    }
    return _gemini_native_video_json(settings.gemini_model, prompt, proxy_videos)


def openai_finalize_promo_edit(
    candidates: list[dict],
    draft: dict,
    gemini_review: dict,
    target_seconds: float = 90.0,
) -> dict:
    if not candidates:
        return {"ok": False, "error": "no candidates"}
    prompt = {
        "task": "Finalize one short-drama promotional edit after GPT draft and Gemini review.",
        "operator_prompt": get_prompt_text("promo_edit_final"),
        "target_seconds": target_seconds,
        "candidates": _compact_promo_candidates(candidates),
        "gpt_draft": draft,
        "gemini_review": gemini_review,
        "final_decision_rules": [
            "Return exactly one final edit plan.",
            "Prioritize narrative continuity and complete dialogue/reaction over isolated dramatic shots.",
            "Use 3-4 candidate scenes, chronological order.",
            "If Gemini reports a continuity risk, either replace that candidate or explain why keeping it still works.",
            "The first selected scene must make the premise understandable within a few seconds.",
            "The last selected scene should end on curiosity, not full resolution.",
        ],
        "return_json": {
            "selected_candidate_ids": ["candidate id numbers in final order"],
            "storyline": "one Chinese sentence describing the final story arc",
            "continuity_notes": "Chinese explanation of continuity choices",
            "opening_text": "short Chinese title, 10 Chinese characters or fewer if possible",
            "ending_text": "short Chinese cliffhanger/CTA",
            "decision_reason": "Chinese summary of how GPT and Gemini were reconciled",
        },
    }
    return _openai_json(prompt)


def gemini_review_frames(
    frame_paths: list[Path],
    transcript: str,
    start_seconds: float,
    end_seconds: float,
) -> dict:
    settings = get_settings()
    if not settings.gemini_api_key:
        return {"ok": False, "score": 0.0, "summary": "", "error": "GEMINI_API_KEY is not configured"}
    if not frame_paths:
        return {"ok": False, "score": 0.0, "summary": "", "error": "no keyframes"}

    prompt = {
        "task": "Review keyframes from a short-drama clip and judge visual highlight value.",
        "operator_prompt": get_prompt_text("visual_frame_review"),
        "time_range_seconds": [start_seconds, end_seconds],
        "transcript_hint": transcript[:3000],
        "scoring_rules": [
            "Strong facial expression, confrontation, action, visual clarity, opening hook.",
            "Penalize visually repetitive or unclear clips.",
        ],
        "return_json": {
            "score": "0-1",
            "summary": "one sentence",
            "visual_signals": ["string"],
            "continuity_risk": "low|medium|high",
        },
    }

    if settings.gemini_api_style.lower() == "native":
        return _gemini_native_json(settings.gemini_model, prompt, frame_paths)
    return _gemini_openai_compatible_json(settings.gemini_model, prompt, frame_paths)


def _chat_json(provider: str, model: str, messages: list[dict]) -> dict:
    settings = get_settings()
    if provider == "openai":
        api_key = settings.openai_api_key
        base_url = _api_base(settings.openai_base_url, "https://api.openai.com")
    else:
        api_key = settings.gemini_api_key
        base_url = _api_base(settings.google_gemini_base_url or settings.gemini_base_url, "")
    if not api_key:
        return {"ok": False, "score": 0.0, "summary": "", "error": f"{provider} api key is not configured"}

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    try:
        response = _post_with_retry(
            f"{base_url}/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json_payload=payload,
            timeout=120,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        parsed = _parse_json_content(content)
        parsed["ok"] = True
        parsed["raw_content"] = content
        return parsed
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "score": 0.0, "summary": "", "error": str(exc)}


def _responses_json(model: str, input_text: str) -> dict:
    settings = get_settings()
    if not settings.openai_api_key:
        return {"ok": False, "score": 0.0, "summary": "", "error": "OPENAI_API_KEY is not configured"}
    base_url = _api_base(settings.openai_base_url, "https://api.openai.com")
    payload = {
        "model": model,
        "input": input_text,
        "temperature": 0.2,
    }
    try:
        response = _post_with_retry(
            f"{base_url}/v1/responses",
            headers={"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"},
            json_payload=payload,
            timeout=120,
        )
        response.raise_for_status()
        text = _extract_response_text(response.json())
        parsed = _parse_json_content(text)
        parsed["ok"] = True
        parsed["raw_content"] = text
        return parsed
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "score": 0.0, "summary": "", "error": str(exc)}


def _openai_json(prompt: dict) -> dict:
    settings = get_settings()
    content = "Return concise valid JSON only.\n" + json.dumps(prompt, ensure_ascii=False)
    if settings.openai_wire_api.lower() == "responses":
        return _responses_json(settings.openai_text_model, content)
    return _chat_json(
        provider="openai",
        model=settings.openai_text_model,
        messages=[
            {"role": "system", "content": "Return concise valid JSON only."},
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
    )


def _gemini_text_json(model: str, prompt: dict) -> dict:
    settings = get_settings()
    base_url = _api_base(settings.google_gemini_base_url or settings.gemini_base_url, "https://generativelanguage.googleapis.com")
    payload = {
        "contents": [{"role": "user", "parts": [{"text": json.dumps(prompt, ensure_ascii=False)}]}],
        "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
    }
    try:
        response = _post_with_retry(
            f"{base_url}/v1beta/models/{model}:generateContent",
            headers={"x-goog-api-key": settings.gemini_api_key, "Content-Type": "application/json"},
            json_payload=payload,
            timeout=120,
        )
        response.raise_for_status()
        text = _extract_gemini_text(response.json())
        parsed = _parse_json_content(text)
        parsed["ok"] = True
        parsed["raw_content"] = text
        return parsed
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def _compact_promo_candidates(candidates: list[dict]) -> list[dict]:
    compact = []
    for item in candidates:
        transcript = item.get("transcript") or {}
        visual = item.get("visual") or {}
        classification = item.get("classification") or {}
        compact.append(
            {
                "id": item.get("candidate_id"),
                "video_name": (item.get("video") or {}).get("name"),
                "sequence": item.get("sequence"),
                "analysis_range_seconds": [item.get("start"), item.get("end")],
                "planned_cut_range_seconds": [item.get("cut_start"), item.get("cut_end")],
                "planned_cut_duration_seconds": item.get("cut_duration"),
                "role": item.get("role"),
                "score": item.get("score"),
                "transcript": str(transcript.get("text") or "")[:1600],
                "visual_summary": str(visual.get("summary") or "")[:700],
                "classification_reason": str(classification.get("reason") or "")[:700],
                "opening_strength": classification.get("opening_strength"),
                "cliffhanger_strength": classification.get("cliffhanger_strength"),
            }
        )
    return compact


def _gemini_openai_compatible_json(model: str, prompt: dict, frame_paths: list[Path]) -> dict:
    content: list[dict[str, Any]] = [
        {"type": "text", "text": json.dumps(prompt, ensure_ascii=False)}
    ]
    for frame_path in frame_paths:
        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{_read_b64(frame_path)}"
                },
            }
        )
    return _chat_json(
        provider="gemini",
        model=model,
        messages=[
            {"role": "system", "content": "Return concise valid JSON only."},
            {"role": "user", "content": content},
        ],
    )


def _gemini_native_json(model: str, prompt: dict, frame_paths: list[Path]) -> dict:
    settings = get_settings()
    base_url = _api_base(settings.google_gemini_base_url or settings.gemini_base_url, "https://generativelanguage.googleapis.com")
    parts: list[dict[str, Any]] = [{"text": json.dumps(prompt, ensure_ascii=False)}]
    for frame_path in frame_paths:
        parts.append(
            {
                "inline_data": {
                    "mime_type": "image/jpeg",
                    "data": _read_b64(frame_path),
                }
            }
        )
    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
    }
    url = f"{base_url}/v1beta/models/{model}:generateContent"
    try:
        response = _post_with_retry(
            url,
            headers={"x-goog-api-key": settings.gemini_api_key, "Content-Type": "application/json"},
            json_payload=payload,
            timeout=120,
        )
        response.raise_for_status()
        text = _extract_gemini_text(response.json())
        parsed = _parse_json_content(text)
        parsed["ok"] = True
        parsed["raw_content"] = text
        return parsed
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "score": 0.0, "summary": "", "error": str(exc)}


def _gemini_native_video_json(model: str, prompt: dict, proxy_videos: list[dict]) -> dict:
    settings = get_settings()
    base_url = _api_base(settings.google_gemini_base_url or settings.gemini_base_url, "https://generativelanguage.googleapis.com")
    parts: list[dict[str, Any]] = [{"text": json.dumps(prompt, ensure_ascii=False)}]
    for item in proxy_videos:
        path = Path(str(item.get("proxy_path") or ""))
        if not path.exists():
            return {"ok": False, "error": f"proxy video not found: {path}"}
        parts.append(
            {
                "inline_data": {
                    "mime_type": _video_mime(path),
                    "data": _read_b64(path),
                }
            }
        )
    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"temperature": 0.15, "responseMimeType": "application/json"},
    }
    try:
        response = _post_with_retry(
            f"{base_url}/v1beta/models/{model}:generateContent",
            headers={"x-goog-api-key": settings.gemini_api_key, "Content-Type": "application/json"},
            json_payload=payload,
            timeout=300,
        )
        response.raise_for_status()
        text = _extract_gemini_text(response.json())
        parsed = _parse_json_content(text)
        parsed["ok"] = True
        parsed["raw_content"] = text
        return parsed
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def _api_base(base_url: str, default: str) -> str:
    return (base_url or default).rstrip("/")


def _openai_v1_base(base_url: str) -> str:
    base = _api_base(base_url, "https://api.openai.com/v1")
    return base if base.endswith("/v1") else f"{base}/v1"


def _read_b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def _audio_mime(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".mp3":
        return "audio/mpeg"
    if suffix == ".wav":
        return "audio/wav"
    if suffix in {".m4a", ".mp4"}:
        return "audio/mp4"
    return "audio/mpeg"


def _image_mime(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".webp":
        return "image/webp"
    if suffix == ".gif":
        return "image/gif"
    return "image/png"


def _video_mime(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".mov", ".qt"}:
        return "video/quicktime"
    if suffix == ".webm":
        return "video/webm"
    if suffix == ".mkv":
        return "video/x-matroska"
    return "video/mp4"


def _parse_json_content(content: str) -> dict:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {"value": value}
    except json.JSONDecodeError:
        return {"summary": text[:1000], "score": 0.0}


def _extract_response_text(payload: dict) -> str:
    parts = []
    for item in payload.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"} and content.get("text"):
                parts.append(content["text"])
    if parts:
        return "\n".join(parts)
    if payload.get("output_text"):
        return str(payload["output_text"])
    return json.dumps(payload, ensure_ascii=False)


def _extract_gemini_text(payload: dict) -> str:
    return payload["candidates"][0]["content"]["parts"][0]["text"]


def _extract_gemini_audio_b64(payload: dict) -> str:
    candidates = payload.get("candidates") or []
    for candidate in candidates:
        content = candidate.get("content") or {}
        for part in content.get("parts") or []:
            inline_data = part.get("inlineData") or part.get("inline_data") or {}
            data = inline_data.get("data")
            if data:
                return data
    return ""


def _write_pcm_wav(path: Path, pcm: bytes, sample_rate: int, channels: int, sample_width: int) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(sample_width)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm)
