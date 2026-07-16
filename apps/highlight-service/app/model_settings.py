from __future__ import annotations

from .config import get_settings
from .db import connect
from .models import ModelSettingsUpdate


SETTING_FIELDS = (
    "openai_api_key",
    "openai_base_url",
    "openai_text_model",
    "openai_image_model",
    "openai_wire_api",
    "openai_transcribe_model",
    "gemini_api_key",
    "google_gemini_base_url",
    "gemini_base_url",
    "gemini_model",
    "gemini_tts_model",
    "gemini_tts_voice",
    "gemini_api_style",
    "transcribe_provider",
)

USAGE_NODES = [
    {
        "key": "transcription",
        "name": "音频转写",
        "stage": "素材理解",
        "provider": "dynamic",
        "model_field": "transcribe_provider",
        "description": "从视频音轨提取台词。可在 Gemini 和 OpenAI Whisper 之间切换。",
    },
    {
        "key": "transcript_analysis",
        "name": "台词高光分析",
        "stage": "素材理解",
        "provider": "openai",
        "model_field": "openai_text_model",
        "description": "分析台词信息密度、冲突和高光区间。",
    },
    {
        "key": "promo_classification",
        "name": "推广片段分类",
        "stage": "剪辑决策",
        "provider": "openai",
        "model_field": "openai_text_model",
        "description": "判断候选片段的剧情作用与推广价值。",
    },
    {
        "key": "promo_draft",
        "name": "推广剪辑草案",
        "stage": "剪辑决策",
        "provider": "openai",
        "model_field": "openai_text_model",
        "description": "根据候选片段生成初版剪辑方案。",
    },
    {
        "key": "visual_review",
        "name": "关键帧画面复核",
        "stage": "视觉复核",
        "provider": "gemini",
        "model_field": "gemini_model",
        "description": "结合关键帧判断画面价值与连续性风险。",
    },
    {
        "key": "video_review",
        "name": "代理视频审片",
        "stage": "视觉复核",
        "provider": "gemini",
        "model_field": "gemini_model",
        "description": "观看低清代理视频，给出剧情精剪保留和删除区间。",
    },
    {
        "key": "promo_review",
        "name": "剪辑草案审核",
        "stage": "剪辑决策",
        "provider": "gemini",
        "model_field": "gemini_model",
        "description": "复核 GPT 草案的连续性、节奏和吸引力。",
    },
    {
        "key": "promo_finalize",
        "name": "最终剪辑决策",
        "stage": "剪辑决策",
        "provider": "openai",
        "model_field": "openai_text_model",
        "description": "综合草案与 Gemini 审核，输出最终剪辑方案。",
    },
    {
        "key": "content_promotion",
        "name": "推广文案生成",
        "stage": "内容生成",
        "provider": "openai",
        "model_field": "openai_text_model",
        "description": "生成标题、正文、话题和宣传图提示词。",
    },
    {
        "key": "image_generation",
        "name": "宣传图与片头片尾",
        "stage": "内容生成",
        "provider": "openai",
        "model_field": "openai_image_model",
        "description": "生成推广图片、封面以及片头片尾视觉素材。",
    },
    {
        "key": "tts",
        "name": "结尾口播合成",
        "stage": "内容生成",
        "provider": "gemini",
        "model_field": "gemini_tts_model",
        "description": "为推广视频生成结尾行动引导口播。",
    },
]


def load_model_settings() -> None:
    settings = get_settings()
    with connect() as conn:
        rows = conn.execute("SELECT key, value FROM model_settings").fetchall()
    for row in rows:
        if row["key"] in SETTING_FIELDS:
            setattr(settings, row["key"], row["value"])


def get_model_settings() -> dict:
    settings = get_settings()
    return {
        "openai": {
            "api_key_configured": bool(settings.openai_api_key),
            "base_url": settings.openai_base_url,
            "text_model": settings.openai_text_model,
            "image_model": settings.openai_image_model,
            "wire_api": settings.openai_wire_api,
            "transcribe_model": settings.openai_transcribe_model,
        },
        "gemini": {
            "api_key_configured": bool(settings.gemini_api_key),
            "base_url": settings.google_gemini_base_url or settings.gemini_base_url,
            "model": settings.gemini_model,
            "tts_model": settings.gemini_tts_model,
            "tts_voice": settings.gemini_tts_voice,
            "api_style": settings.gemini_api_style,
        },
        "transcribe_provider": settings.transcribe_provider,
        "usage_nodes": USAGE_NODES,
    }


def update_model_settings(payload: ModelSettingsUpdate) -> dict:
    settings = get_settings()
    values = {
        "openai_base_url": payload.openai_base_url.strip(),
        "openai_text_model": payload.openai_text_model.strip(),
        "openai_image_model": payload.openai_image_model.strip(),
        "openai_wire_api": payload.openai_wire_api,
        "openai_transcribe_model": payload.openai_transcribe_model.strip(),
        "gemini_base_url": payload.gemini_base_url.strip(),
        "google_gemini_base_url": "",
        "gemini_model": payload.gemini_model.strip(),
        "gemini_tts_model": payload.gemini_tts_model.strip(),
        "gemini_tts_voice": payload.gemini_tts_voice.strip(),
        "gemini_api_style": payload.gemini_api_style,
        "transcribe_provider": payload.transcribe_provider,
    }
    if payload.clear_openai_api_key:
        values["openai_api_key"] = ""
    elif payload.openai_api_key and payload.openai_api_key.strip():
        values["openai_api_key"] = payload.openai_api_key.strip()
    if payload.clear_gemini_api_key:
        values["gemini_api_key"] = ""
    elif payload.gemini_api_key and payload.gemini_api_key.strip():
        values["gemini_api_key"] = payload.gemini_api_key.strip()

    with connect() as conn:
        conn.executemany(
            """
            INSERT INTO model_settings (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
            """,
            values.items(),
        )
    for key, value in values.items():
        setattr(settings, key, value)
    return get_model_settings()
