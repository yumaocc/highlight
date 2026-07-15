from __future__ import annotations

from fastapi import HTTPException

from .db import connect, rows_to_dicts
from .models import IntroTemplateCreate, IntroTemplateUpdate


def list_intro_templates() -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM intro_templates ORDER BY updated_at DESC, id DESC").fetchall()
    return rows_to_dicts(rows)


def get_intro_template(template_id: int) -> dict:
    with connect() as conn:
        row = conn.execute("SELECT * FROM intro_templates WHERE id = ?", (template_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="intro template not found")
    return dict(row)


def create_intro_template(payload: IntroTemplateCreate) -> dict:
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO intro_templates
                (
                    name, drama_name, style, summary, duration, asset_path,
                    image_path, image_url, intro_image_path, intro_image_url,
                    outro_image_path, outro_image_url, prompt, source, status
                )
            VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.name,
                payload.drama_name,
                payload.style,
                payload.summary,
                payload.duration,
                payload.asset_path,
                payload.image_path,
                payload.image_url,
                payload.intro_image_path,
                payload.intro_image_url,
                payload.outro_image_path,
                payload.outro_image_url,
                payload.prompt,
                payload.source,
                payload.status,
            ),
        )
        template_id = int(cursor.lastrowid)
    return get_intro_template(template_id)


def update_intro_template(template_id: int, payload: IntroTemplateUpdate) -> dict:
    current = get_intro_template(template_id)
    values = payload.model_dump(exclude_unset=True)
    if not values:
        return current

    assignments = []
    params = []
    for field, value in values.items():
        assignments.append(f"{field} = ?")
        params.append(value)
    assignments.append("updated_at = CURRENT_TIMESTAMP")
    params.append(template_id)

    with connect() as conn:
        conn.execute(f"UPDATE intro_templates SET {', '.join(assignments)} WHERE id = ?", params)
    return get_intro_template(template_id)


def delete_intro_template(template_id: int) -> dict:
    get_intro_template(template_id)
    with connect() as conn:
        conn.execute("DELETE FROM intro_templates WHERE id = ?", (template_id,))
    return {"deleted": True, "id": template_id}
