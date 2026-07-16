import sqlite3
from pathlib import Path
from typing import Iterable

from .config import get_settings


SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER,
    path TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    duration REAL,
    width INTEGER,
    height INTEGER,
    fps REAL,
    codec TEXT,
    status TEXT NOT NULL DEFAULT 'indexed',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS clips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER NOT NULL,
    start_seconds REAL NOT NULL,
    end_seconds REAL NOT NULL,
    score REAL,
    reason TEXT,
    output_path TEXT,
    status TEXT NOT NULL DEFAULT 'created',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(video_id) REFERENCES videos(id)
);

CREATE TABLE IF NOT EXISTS generated_assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    source_video_id INTEGER,
    clip_id INTEGER,
    pipeline_run_id INTEGER,
    pipeline_step_id INTEGER,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    output_path TEXT NOT NULL,
    download_url TEXT NOT NULL DEFAULT '',
    duration REAL,
    status TEXT NOT NULL DEFAULT 'exported',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(project_id) REFERENCES projects(id),
    FOREIGN KEY(source_video_id) REFERENCES videos(id),
    FOREIGN KEY(clip_id) REFERENCES clips(id)
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    source_video_id INTEGER,
    template_key TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    current_step TEXT NOT NULL DEFAULT '',
    progress INTEGER NOT NULL DEFAULT 0,
    params_json TEXT NOT NULL DEFAULT '{}',
    prompt_snapshot_json TEXT NOT NULL DEFAULT '{}',
    result_json TEXT NOT NULL DEFAULT '{}',
    error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at TEXT,
    finished_at TEXT,
    FOREIGN KEY(project_id) REFERENCES projects(id),
    FOREIGN KEY(source_video_id) REFERENCES videos(id)
);

CREATE TABLE IF NOT EXISTS pipeline_run_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    project_id INTEGER NOT NULL,
    source_video_id INTEGER NOT NULL,
    order_index INTEGER NOT NULL,
    role TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(run_id) REFERENCES pipeline_runs(id),
    FOREIGN KEY(project_id) REFERENCES projects(id),
    FOREIGN KEY(source_video_id) REFERENCES videos(id)
);

CREATE TABLE IF NOT EXISTS pipeline_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    project_id INTEGER NOT NULL,
    source_video_id INTEGER,
    step_key TEXT NOT NULL,
    name TEXT NOT NULL,
    order_index INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    progress INTEGER NOT NULL DEFAULT 0,
    input_json TEXT NOT NULL DEFAULT '{}',
    output_json TEXT NOT NULL DEFAULT '{}',
    error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at TEXT,
    finished_at TEXT,
    FOREIGN KEY(run_id) REFERENCES pipeline_runs(id),
    FOREIGN KEY(project_id) REFERENCES projects(id),
    FOREIGN KEY(source_video_id) REFERENCES videos(id)
);

CREATE TABLE IF NOT EXISTS pipeline_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    priority INTEGER NOT NULL DEFAULT 100,
    locked_by TEXT NOT NULL DEFAULT '',
    locked_at TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(run_id) REFERENCES pipeline_runs(id)
);

CREATE TABLE IF NOT EXISTS artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    source_video_id INTEGER,
    pipeline_run_id INTEGER,
    pipeline_step_id INTEGER,
    type TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    path TEXT NOT NULL DEFAULT '',
    content_json TEXT NOT NULL DEFAULT '{}',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    is_final INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(project_id) REFERENCES projects(id),
    FOREIGN KEY(source_video_id) REFERENCES videos(id),
    FOREIGN KEY(pipeline_run_id) REFERENCES pipeline_runs(id),
    FOREIGN KEY(pipeline_step_id) REFERENCES pipeline_steps(id)
);

CREATE TABLE IF NOT EXISTS prompt_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'video_generation',
    description TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    is_system INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS auto_publish_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    drama_name TEXT NOT NULL,
    normalized_name TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'published',
    project_id INTEGER,
    auto_task_id TEXT NOT NULL DEFAULT '',
    publish_task_id TEXT NOT NULL DEFAULT '',
    message TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS auto_publish_tasks (
    id TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL DEFAULT '{}',
    task_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS model_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def db_path() -> Path:
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings.data_dir / "app.sqlite"


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path(), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        _migrate_schema(conn)
        _seed_default_project(conn)
        _seed_prompt_configs(conn)


def rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict]:
    return [dict(row) for row in rows]


def _migrate_schema(conn: sqlite3.Connection) -> None:
    video_columns = _table_columns(conn, "videos")
    if "project_id" not in video_columns:
        conn.execute("ALTER TABLE videos ADD COLUMN project_id INTEGER")
    asset_columns = _table_columns(conn, "generated_assets")
    if "pipeline_run_id" not in asset_columns:
        conn.execute("ALTER TABLE generated_assets ADD COLUMN pipeline_run_id INTEGER")
    if "pipeline_step_id" not in asset_columns:
        conn.execute("ALTER TABLE generated_assets ADD COLUMN pipeline_step_id INTEGER")
    pipeline_run_columns = _table_columns(conn, "pipeline_runs")
    if "prompt_snapshot_json" not in pipeline_run_columns:
        conn.execute("ALTER TABLE pipeline_runs ADD COLUMN prompt_snapshot_json TEXT NOT NULL DEFAULT '{}'")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pipeline_run_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            project_id INTEGER NOT NULL,
            source_video_id INTEGER NOT NULL,
            order_index INTEGER NOT NULL,
            role TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(run_id) REFERENCES pipeline_runs(id),
            FOREIGN KEY(project_id) REFERENCES projects(id),
            FOREIGN KEY(source_video_id) REFERENCES videos(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS auto_publish_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            drama_name TEXT NOT NULL,
            normalized_name TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'published',
            project_id INTEGER,
            auto_task_id TEXT NOT NULL DEFAULT '',
            publish_task_id TEXT NOT NULL DEFAULT '',
            message TEXT NOT NULL DEFAULT '',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(project_id) REFERENCES projects(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS auto_publish_tasks (
            id TEXT PRIMARY KEY,
            payload_json TEXT NOT NULL DEFAULT '{}',
            task_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row["name"] for row in rows}


def _seed_default_project(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT id FROM projects ORDER BY id LIMIT 1").fetchone()
    if not row:
        cursor = conn.execute(
            """
            INSERT INTO projects (name, description, status)
            VALUES ('默认短剧项目', '兼容旧上传和生成流程的默认项目。', 'active')
            """
        )
        project_id = cursor.lastrowid
    else:
        project_id = row["id"]
    conn.execute("UPDATE videos SET project_id = ? WHERE project_id IS NULL", (project_id,))


DEFAULT_PROMPT_CONFIGS = [
    {
        "key": "transcribe_audio",
        "name": "音频转写",
        "description": "Gemini 音频转写时使用，要求输出短剧中文台词 JSON。",
        "content": (
            "请转写这段短剧音频里的中文台词。"
            "只返回 JSON，格式为 {\"transcript\":\"...\",\"ok\":true,\"notes\":\"...\"}。"
            "如果听不清，ok=false，并在 notes 说明原因。"
        ),
    },
    {
        "key": "highlight_transcript_review",
        "name": "高光台词分析",
        "description": "GPT 根据转写台词判断高光价值、钩子和剧情连续性。",
        "content": (
            "分析短剧片段台词的高光价值。优先冲突、反转、情绪爆发、强钩子台词和悬念，"
            "但剧情连续性比单个高能瞬间更重要。避免只因为音量大就判定为高光。"
        ),
    },
    {
        "key": "promo_segment_classification",
        "name": "推广片段分类",
        "description": "把候选窗口分类为 hook、关系、冲突、反转、悬念等推广角色。",
        "content": (
            "把短剧片段分类为推广视频素材，而不是普通高光。目标是快速让观众理解人物关系、"
            "核心冲突和继续看全集的理由。优先能开场抓人、交代关系、制造冲突、反转或悬念收尾的片段。"
        ),
    },
    {
        "key": "promo_edit_draft",
        "name": "推广剪辑草案",
        "description": "GPT 从候选片段里生成剧情引流视频剪辑草案。",
        "content": (
            "从候选片段中创建短剧推广剪辑方案。成片应该让观众想看全集，不是随机高光合集。"
            "选择 3-4 个候选镜头，按故事时间线组织，优先人物关系、冲突、反转或悬念。"
            "连续性比最高分更重要，避免截断台词或反应。"
        ),
    },
    {
        "key": "promo_edit_review",
        "name": "推广剪辑复核",
        "description": "Gemini 复核 GPT 剪辑草案的连续性和吸引力。",
        "content": (
            "作为短剧连续性剪辑师复核推广剪辑草案。检查是否起点太晚、结尾太早、打断台词、"
            "跳过关键反应或让新观众看不懂。只能从候选 id 中建议替换。"
        ),
    },
    {
        "key": "promo_edit_final",
        "name": "推广最终决策",
        "description": "GPT 综合草案和 Gemini 复核后输出最终剪辑方案。",
        "content": (
            "综合 GPT 草案和 Gemini 复核，输出唯一最终短剧推广剪辑方案。"
            "优先剧情连续性和完整台词/反应，使用 3-4 个候选片段，按时间线排列。"
            "开头必须几秒内让人理解看点，结尾留悬念而不是完整解决。"
        ),
    },
    {
        "key": "visual_frame_review",
        "name": "关键帧画面复评",
        "description": "Gemini 根据关键帧判断画面高光价值和连续性风险。",
        "content": (
            "复核短剧片段关键帧的画面高光价值。关注强表情、对峙、动作、视觉清晰度和开场钩子。"
            "惩罚重复、模糊、信息不足或连续性风险高的画面。"
        ),
    },
    {
        "key": "story_quality_cut_review",
        "name": "剧情精剪审片",
        "description": "Gemini 基于低清代理视频判断剧情精剪的保留和删除时间段。",
        "content": (
            "你是短剧剧情精剪剪辑师。目标不是做引流预告，也不是压到固定时长，"
            "而是删除低质量、重复、无信息量、停顿过长或不推进剧情的片段，"
            "保留能维持剧情理解、人物关系、冲突铺垫、反转、情绪反应和悬念的内容。"
            "必须识别并删除原始素材自带的片尾、平台落版、未完待续、下集更精彩、关注点赞收藏、"
            "点击左下角看全集、看全集、重复宣传卡、黑屏/定帧结束页、演员表或片尾字幕；"
            "不要因为这些片尾有文字、音乐或强 CTA 就保留。"
            "如果原片结尾同时包含真实剧情信息，只保留剧情相关部分，丢弃宣传片尾和结束卡部分。"
            "输出必须按原集数和时间线给出 keep_required、keep_optional、drop 决策。"
        ),
    },
    {
        "key": "ending_voiceover_style",
        "name": "结尾口播风格",
        "description": "推广视频结尾 TTS 的口吻风格。",
        "content": "用短剧推广口吻，女声，略带悬念和催促感，语速偏快但清晰",
    },
]


def _seed_prompt_configs(conn: sqlite3.Connection) -> None:
    for item in DEFAULT_PROMPT_CONFIGS:
        conn.execute(
            """
            INSERT INTO prompt_configs
                (key, name, category, description, content, enabled, is_system)
            VALUES
                (?, ?, 'video_generation', ?, ?, 1, 1)
            ON CONFLICT(key) DO NOTHING
            """,
            (item["key"], item["name"], item["description"], item["content"]),
        )
