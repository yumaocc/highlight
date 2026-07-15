from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Optional

from fastapi import HTTPException

from .config import get_settings
from .db import connect, rows_to_dicts
from .models import ProjectCreate, ProjectUpdate


DEFAULT_PROJECT_NAME = "默认短剧项目"
DEFAULT_PUBLISH_TAGS = ["#快来看短剧", "#AI创想家计划", "#神仙剪刀手"]
LEGACY_QUALITY_COPY_MARKER = "他一出手，全场都以为只是保镖，直到真正身份藏不住了。"


def ensure_default_project() -> dict:
    with connect() as conn:
        row = conn.execute("SELECT * FROM projects ORDER BY id LIMIT 1").fetchone()
        if row:
            project = dict(row)
        else:
            cursor = conn.execute(
                """
                INSERT INTO projects (name, description, status)
                VALUES (?, ?, 'active')
                """,
                (DEFAULT_PROJECT_NAME, "兼容旧上传和生成流程的默认项目。"),
            )
            project = dict(conn.execute("SELECT * FROM projects WHERE id = ?", (cursor.lastrowid,)).fetchone())
        conn.execute("UPDATE videos SET project_id = ? WHERE project_id IS NULL", (project["id"],))
    return project


def resolve_project_id(project_id: Optional[int] = None) -> int:
    if project_id:
        get_project(project_id)
        return project_id
    return int(ensure_default_project()["id"])


def list_projects() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
                p.*,
                COUNT(DISTINCT v.id) AS video_count,
                COUNT(DISTINCT a.id) AS asset_count
            FROM projects p
            LEFT JOIN videos v ON v.project_id = p.id
            LEFT JOIN generated_assets a ON a.project_id = p.id
            GROUP BY p.id
            ORDER BY p.updated_at DESC, p.id DESC
            """
        ).fetchall()
    return rows_to_dicts(rows)


def get_project(project_id: int) -> dict:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT
                p.*,
                COUNT(DISTINCT v.id) AS video_count,
                COUNT(DISTINCT a.id) AS asset_count
            FROM projects p
            LEFT JOIN videos v ON v.project_id = p.id
            LEFT JOIN generated_assets a ON a.project_id = p.id
            WHERE p.id = ?
            GROUP BY p.id
            """,
            (project_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="project not found")
    return dict(row)


def create_project(payload: ProjectCreate) -> dict:
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO projects (name, description, status)
            VALUES (?, ?, ?)
            """,
            (payload.name, payload.description, payload.status),
        )
        project_id = int(cursor.lastrowid)
    return get_project(project_id)


def update_project(project_id: int, payload: ProjectUpdate) -> dict:
    get_project(project_id)
    values = payload.model_dump(exclude_unset=True)
    if not values:
        return get_project(project_id)

    assignments = []
    params = []
    for field, value in values.items():
        assignments.append(f"{field} = ?")
        params.append(value)
    assignments.append("updated_at = CURRENT_TIMESTAMP")
    params.append(project_id)
    with connect() as conn:
        conn.execute(f"UPDATE projects SET {', '.join(assignments)} WHERE id = ?", params)
    return get_project(project_id)


def delete_project(project_id: int) -> dict:
    default_project_id = resolve_project_id(None)
    if project_id == default_project_id:
        raise HTTPException(status_code=400, detail="default project cannot be deleted")
    get_project(project_id)
    settings = get_settings()
    removed_input_files = 0
    removed_work_dirs = 0
    failed: list[str] = []
    with connect() as conn:
        related = conn.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM videos WHERE project_id = ?) AS video_count,
                (SELECT COUNT(*) FROM generated_assets WHERE project_id = ?) AS asset_count,
                (
                    SELECT COUNT(*)
                    FROM pipeline_runs
                    WHERE project_id = ? AND status IN ('pending', 'running')
                ) AS active_run_count
            """,
            (project_id, project_id, project_id),
        ).fetchone()
        if related["active_run_count"]:
            raise HTTPException(status_code=400, detail="project has pending or running pipeline tasks")
        video_rows = conn.execute("SELECT id FROM videos WHERE project_id = ?", (project_id,)).fetchall()
        run_rows = conn.execute("SELECT id FROM pipeline_runs WHERE project_id = ?", (project_id,)).fetchall()
        video_ids = [int(row["id"]) for row in video_rows]
        run_ids = [int(row["id"]) for row in run_rows]
        if run_ids:
            placeholders = ",".join("?" for _ in run_ids)
            conn.execute(f"DELETE FROM pipeline_jobs WHERE run_id IN ({placeholders})", run_ids)
            conn.execute(f"DELETE FROM artifacts WHERE pipeline_run_id IN ({placeholders})", run_ids)
            conn.execute(f"DELETE FROM pipeline_steps WHERE run_id IN ({placeholders})", run_ids)
            conn.execute(f"DELETE FROM pipeline_run_sources WHERE run_id IN ({placeholders})", run_ids)
        conn.execute("DELETE FROM generated_assets WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM artifacts WHERE project_id = ?", (project_id,))
        if video_ids:
            placeholders = ",".join("?" for _ in video_ids)
            conn.execute(f"DELETE FROM clips WHERE video_id IN ({placeholders})", video_ids)
        conn.execute("DELETE FROM pipeline_runs WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM videos WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))

    project_input_dir = settings.input_dir / f"project_{project_id}"
    if project_input_dir.exists():
        for path in project_input_dir.rglob("*"):
            if path.is_file():
                removed_input_files += 1
        try:
            shutil.rmtree(project_input_dir)
        except Exception as exc:  # noqa: BLE001 - return cleanup errors to the UI.
            failed.append(f"{project_input_dir}: {exc}")

    removed_work_dirs, work_failures = _remove_project_work_dirs(settings.work_dir, run_ids)
    failed.extend(work_failures)

    return {
        "deleted": True,
        "id": project_id,
        "removed_videos": int(related["video_count"] or 0),
        "removed_assets": int(related["asset_count"] or 0),
        "removed_runs": len(run_ids),
        "removed_input_files": removed_input_files,
        "removed_work_dirs": removed_work_dirs,
        "outputs_preserved": str(settings.output_dir.parent),
        "failed": failed,
    }


def list_project_assets(project_id: Optional[int] = None) -> list[dict]:
    resolved_project_id = resolve_project_id(project_id)
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT a.*, v.name AS source_video_name
            FROM generated_assets a
            LEFT JOIN videos v ON v.id = a.source_video_id
            WHERE a.project_id = ?
            ORDER BY a.created_at DESC, a.id DESC
            """,
            (resolved_project_id,),
        ).fetchall()
    return [_normalize_asset(row) for row in rows_to_dicts(rows)]


def record_generated_asset(
    *,
    project_id: int,
    asset_type: str,
    title: str,
    output_path: Path,
    download_url: str,
    source_video_id: Optional[int] = None,
    clip_id: Optional[int] = None,
    pipeline_run_id: Optional[int] = None,
    pipeline_step_id: Optional[int] = None,
    description: str = "",
    duration: Optional[float] = None,
    metadata: Optional[dict] = None,
) -> dict:
    metadata_json = json.dumps(metadata or {}, ensure_ascii=False, default=str)
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO generated_assets
                (
                    project_id,
                    source_video_id,
                    clip_id,
                    pipeline_run_id,
                    pipeline_step_id,
                    type,
                    title,
                    description,
                    output_path,
                    download_url,
                    duration,
                    status,
                    metadata_json
                )
            VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'exported', ?)
            """,
            (
                project_id,
                source_video_id,
                clip_id,
                pipeline_run_id,
                pipeline_step_id,
                asset_type,
                title,
                description,
                str(output_path),
                download_url,
                duration,
                metadata_json,
            ),
        )
        asset_id = int(cursor.lastrowid)
        conn.execute("UPDATE projects SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (project_id,))
        row = conn.execute(
            """
            SELECT a.*, v.name AS source_video_name
            FROM generated_assets a
            LEFT JOIN videos v ON v.id = a.source_video_id
            WHERE a.id = ?
            """,
            (asset_id,),
        ).fetchone()
    return _normalize_asset(dict(row))


def _normalize_asset(row: dict) -> dict:
    metadata = {}
    try:
        metadata = json.loads(row.get("metadata_json") or "{}")
    except json.JSONDecodeError:
        metadata = {}
    metadata = _ensure_promo_copy(row, metadata)
    return {
        **row,
        "metadata": metadata,
    }


def _ensure_promo_copy(row: dict, metadata: dict) -> dict:
    asset_type = str(row.get("type") or "")
    if metadata.get("promo_copy") and not (
        asset_type == "quality_cut" and LEGACY_QUALITY_COPY_MARKER in str(metadata.get("promo_copy") or "")
    ):
        metadata = dict(metadata)
        metadata["publish_tags"] = _ensure_publish_tags(metadata.get("publish_tags"), asset_type)
        return metadata
    if asset_type not in {"promo", "quality_cut", "highlight"}:
        return metadata
    title = str(row.get("title") or "短剧高能片段")
    description = str(row.get("description") or "")
    if asset_type == "quality_cut":
        clean_title = title.replace("剧情精剪", "").strip(" -_") or "这部短剧"
        copy = _quality_cut_fallback_copy(clean_title)
    elif asset_type == "promo":
        hook = description or "本以为只是一次普通相遇，没想到从这里开始全员命运都被改写"
        copy = f"{hook}。身份、误会和旧账一起爆开，每一个眼神都像在埋下一次反转。"
    else:
        copy = f"《{title}》这一幕太上头了，话刚说出口，局势就彻底变了。错过前面还能补，错过这里真的亏。"
    metadata = dict(metadata)
    metadata["promo_copy_title"] = "宣传文案"
    metadata["promo_copy"] = copy
    metadata["publish_tags"] = _ensure_publish_tags(metadata.get("publish_tags"), asset_type)
    return metadata


def _quality_cut_fallback_copy(clean_title: str) -> str:
    if any(word in clean_title for word in ("遗嘱", "继承", "家产")):
        return f"《{clean_title}》一份遗嘱把亲情、旧账和利益全摆上台面，谁是真心谁在算计，很快就藏不住了。"
    if any(word in clean_title for word in ("婚姻", "离婚", "妻", "夫", "千金")):
        return f"《{clean_title}》婚姻里的委屈刚被撕开，隐藏身份和旧账就一起翻涌上来，越到后面越想看她怎么反击。"
    if any(word in clean_title for word in ("上海滩", "风云", "江湖")):
        return f"《{clean_title}》乱局里各方势力步步紧逼，旧恩怨和新危机接连爆开，真正的较量才刚开始。"
    if any(word in clean_title for word in ("保安", "保镖", "总裁", "女神", "求婚")):
        return f"《{clean_title}》身份差距和意外求婚把局面瞬间点燃，旁人的轻视越重，后面的反转越狠。"
    return f"《{clean_title}》人物关系刚被撕开，新的危机就追了上来。每一段对话都在把真相推向失控边缘。"


def _ensure_publish_tags(tags: object, asset_type: str) -> list[str]:
    defaults = [*DEFAULT_PUBLISH_TAGS, "#短剧", "#追剧"]
    if asset_type == "quality_cut":
        defaults.extend(["#剧情精剪", "#高能剧情"])
    elif asset_type == "promo":
        defaults.extend(["#短剧推荐", "#高能反转"])
    elif asset_type == "highlight":
        defaults.extend(["#高能片段", "#名场面"])
    values = tags if isinstance(tags, list) else []
    normalized = []
    for value in [*defaults, *values]:
        tag = str(value).strip().lstrip("#").strip()
        if not tag:
            continue
        formatted = f"#{tag}"
        if formatted not in normalized:
            normalized.append(formatted)
    return normalized


def _remove_project_work_dirs(work_dir: Path, run_ids: list[int]) -> tuple[int, list[str]]:
    if not run_ids or not work_dir.exists():
        return 0, []
    failed: list[str] = []
    removed = 0
    names = {f"run_{run_id}" for run_id in run_ids}
    names.update(f"story_quality_cut_{run_id}" for run_id in run_ids)
    for parent_name in ("proxy", "clips", "covers", "outros", "review-pack"):
        parent = work_dir / parent_name
        if not parent.exists():
            continue
        for name in names:
            path = parent / name
            if not path.exists() or not path.is_dir():
                continue
            try:
                shutil.rmtree(path)
                removed += 1
            except Exception as exc:  # noqa: BLE001 - surface cleanup failures.
                failed.append(f"{path}: {exc}")
    return removed, failed
