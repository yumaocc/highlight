from __future__ import annotations

from typing import Optional

from fastapi import HTTPException

from .db import DEFAULT_PROMPT_CONFIGS, connect, rows_to_dicts
from .models import PromptConfigCreate, PromptConfigUpdate


DEFAULT_PROMPT_BY_KEY = {item["key"]: item for item in DEFAULT_PROMPT_CONFIGS}


def get_prompt_text(key: str) -> str:
    with connect() as conn:
        row = conn.execute(
            "SELECT content FROM prompt_configs WHERE key = ? AND enabled = 1",
            (key,),
        ).fetchone()
    if row:
        return str(row["content"])
    default = DEFAULT_PROMPT_BY_KEY.get(key)
    return str(default["content"]) if default else ""


def list_prompt_configs(category: Optional[str] = None) -> list[dict]:
    with connect() as conn:
        if category:
            rows = conn.execute(
                "SELECT * FROM prompt_configs WHERE category = ? ORDER BY category, id",
                (category,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM prompt_configs ORDER BY category, id").fetchall()
    return [_normalize_prompt(row) for row in rows_to_dicts(rows)]


def get_prompt_config(prompt_id: int) -> dict:
    with connect() as conn:
        row = conn.execute("SELECT * FROM prompt_configs WHERE id = ?", (prompt_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="prompt config not found")
    return _normalize_prompt(dict(row))


def create_prompt_config(payload: PromptConfigCreate) -> dict:
    with connect() as conn:
        try:
            cursor = conn.execute(
                """
                INSERT INTO prompt_configs
                    (key, name, category, description, content, enabled, is_system)
                VALUES
                    (?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    payload.key,
                    payload.name,
                    payload.category,
                    payload.description,
                    payload.content,
                    int(payload.enabled),
                ),
            )
        except Exception as exc:  # noqa: BLE001 - surface duplicate key as structured API error.
            raise HTTPException(status_code=400, detail=f"failed to create prompt config: {exc}") from exc
        prompt_id = int(cursor.lastrowid)
    return get_prompt_config(prompt_id)


def update_prompt_config(prompt_id: int, payload: PromptConfigUpdate) -> dict:
    current = get_prompt_config(prompt_id)
    values = payload.model_dump(exclude_unset=True)
    if not values:
        return current

    assignments = []
    params = []
    for field, value in values.items():
        assignments.append(f"{field} = ?")
        params.append(int(value) if field == "enabled" else value)
    assignments.append("updated_at = CURRENT_TIMESTAMP")
    params.append(prompt_id)

    with connect() as conn:
        conn.execute(
            f"UPDATE prompt_configs SET {', '.join(assignments)} WHERE id = ?",
            params,
        )
    return get_prompt_config(prompt_id)


def delete_prompt_config(prompt_id: int) -> dict:
    current = get_prompt_config(prompt_id)
    if current["is_system"]:
        raise HTTPException(status_code=400, detail="system prompt configs cannot be deleted; disable or edit it instead")
    with connect() as conn:
        conn.execute("DELETE FROM prompt_configs WHERE id = ?", (prompt_id,))
    return {"deleted": True, "id": prompt_id}


def _normalize_prompt(row: dict) -> dict:
    return {
        **row,
        "enabled": bool(row.get("enabled")),
        "is_system": bool(row.get("is_system")),
    }
