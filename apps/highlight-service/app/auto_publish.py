from __future__ import annotations

from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import re
import time
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any

import httpx

from .baidu_pcs import download_first_episodes_from_baidupcs_share
from .auto_compose import compose_episode_publish_video
from .config import get_settings
from .db import connect, rows_to_dicts
from .models import AutoPublishCreate, DEFAULT_AUTO_PUBLISH_TOPICS, PipelineRunCreate, ProjectCreate
from .pipeline import create_pipeline_runs, get_pipeline_run, list_pipeline_generated_assets, run_next_pipeline_job
from .projects import create_project
from .qingque_resource import qingque_resource_client


AUTO_PUBLISH_TASKS: dict[str, dict[str, Any]] = {}
AUTO_PUBLISH_PAYLOADS: dict[str, AutoPublishCreate] = {}
AUTO_PUBLISH_TASK_LOCK = Lock()


def normalize_drama_name(name: str) -> str:
    return re.sub(r"[\s《》<>【】\[\]（）()·._/\\-]+", "", str(name or "")).lower()


def list_auto_publish_records() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM auto_publish_records ORDER BY created_at DESC, id DESC"
        ).fetchall()
    return [_normalize_record(row) for row in rows_to_dicts(rows)]


def get_auto_publish_record(name: str) -> dict[str, Any] | None:
    normalized = normalize_drama_name(name)
    if not normalized:
        return None
    with connect() as conn:
        row = conn.execute("SELECT * FROM auto_publish_records WHERE normalized_name = ?", (normalized,)).fetchone()
    return _normalize_record(dict(row)) if row else None


def create_auto_publish_task(task_id: str, payload: AutoPublishCreate) -> dict[str, Any]:
    names = dedupe_names(payload.drama_names)
    task = {
        "id": task_id,
        "status": "pending",
        "progress": 0,
        "message": "自动发布任务已创建",
        "total": len(names),
        "completed": 0,
        "items": [_initial_item(name) for name in names],
        "logs": [],
        "created_at": _now_iso(),
        "started_at": None,
        "finished_at": None,
    }
    with AUTO_PUBLISH_TASK_LOCK:
        AUTO_PUBLISH_TASKS[task_id] = task
        AUTO_PUBLISH_PAYLOADS[task_id] = payload.model_copy(deep=True)
    _persist_task(task_id)
    return task


def get_auto_publish_task(task_id: str) -> dict[str, Any]:
    with AUTO_PUBLISH_TASK_LOCK:
        task = AUTO_PUBLISH_TASKS.get(task_id)
        if task:
            return json.loads(json.dumps(task, ensure_ascii=False, default=str))
    return _restore_task(task_id)


def execute_auto_publish_task(task_id: str, payload: AutoPublishCreate) -> None:
    names = dedupe_names(payload.drama_names)
    max_workers = max(1, min(int(payload.max_concurrency or 1), len(names) or 1))
    _update_task(
        task_id,
        status="running",
        started_at=_now_iso(),
        message=f"开始自动处理短剧列表，并发数 {max_workers}",
    )
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="auto-publish") as executor:
        futures = {
            executor.submit(_process_one, task_id, index, name, payload): (index, name)
            for index, name in enumerate(names)
        }
        for future in as_completed(futures):
            index, _name = futures[future]
            try:
                future.result()
            except Exception as exc:  # noqa: BLE001 - preserve per-item failure in long task.
                _update_item(task_id, index, status="failed", progress=100, message=str(exc), error=str(exc))
            _update_task_progress(task_id)
    _finish_task(task_id)


def retry_auto_publish_item(task_id: str, index: int) -> dict[str, Any]:
    if not get_auto_publish_task(task_id):
        raise KeyError("auto publish task not found")
    with AUTO_PUBLISH_TASK_LOCK:
        task = AUTO_PUBLISH_TASKS.get(task_id)
        payload = AUTO_PUBLISH_PAYLOADS.get(task_id)
        if not task or not payload:
            raise KeyError("auto publish task not found")
        items = task.get("items") or []
        if index < 0 or index >= len(items):
            raise IndexError("auto publish item not found")
        item = items[index]
        if item.get("status") != "failed":
            raise ValueError("only failed items can be retried")
        item.update(status="pending", error="", message="等待从失败阶段重试")
        task.update(status="pending", finished_at=None, message=f"准备重试：{item.get('name')}")
        snapshot = json.loads(json.dumps(task, ensure_ascii=False, default=str))
    _persist_task(task_id)
    return snapshot


def execute_auto_publish_retry(task_id: str, index: int) -> None:
    get_auto_publish_task(task_id)
    with AUTO_PUBLISH_TASK_LOCK:
        task = AUTO_PUBLISH_TASKS.get(task_id)
        payload = AUTO_PUBLISH_PAYLOADS.get(task_id)
        if not task or not payload:
            return
        item = task["items"][index]
        name = item["name"]
    _update_task(task_id, status="running", started_at=_now_iso(), message=f"正在重试：{name}")
    try:
        _process_one(task_id, index, name, payload, resume=True)
    except Exception as exc:  # noqa: BLE001 - preserve retry failure on the item.
        _update_item(task_id, index, status="failed", progress=100, message=str(exc), error=str(exc))
    _finish_task(task_id)


def _finish_task(task_id: str) -> None:
    task = get_auto_publish_task(task_id)
    items = task.get("items") or []
    failed = [item for item in items if item.get("status") == "failed"]
    skipped = [item for item in items if item.get("status") == "skipped"]
    succeeded = [item for item in items if item.get("status") == "succeeded"]
    status = "failed" if failed else "succeeded"
    message = f"处理完成：成功 {len(succeeded)}，跳过 {len(skipped)}，失败 {len(failed)}"
    _update_task(
        task_id,
        status=status,
        progress=100,
        completed=len(succeeded) + len(skipped) + len(failed),
        message=message,
        finished_at=_now_iso(),
    )


def dedupe_names(names: list[str]) -> list[str]:
    results: list[str] = []
    seen: set[str] = set()
    for name in names:
        clean = str(name or "").strip()
        normalized = normalize_drama_name(clean)
        if not clean or not normalized or normalized in seen:
            continue
        seen.add(normalized)
        results.append(clean)
    return results


def _process_one(task_id: str, index: int, name: str, payload: AutoPublishCreate, *, resume: bool = False) -> None:
    item_started_at = time.monotonic()
    checkpoint = _item_checkpoint(task_id, index) if resume else {}
    existing = get_auto_publish_record(name) if not resume else None
    if existing and payload.skip_existing:
        _update_item(task_id, index, status="skipped", progress=100, message="同名短剧已发布过", existing_record=existing)
        return

    resource_data = checkpoint.get("resource") or {}
    if resource_data:
        _update_item(task_id, index, status="running", progress=18, message="已复用资源匹配结果")
    else:
        _update_item(task_id, index, status="running", progress=8, message="正在查询青雀资源")
        with _timed_stage(task_id, index, "qingque_lookup", "青雀资源查询"):
            matches = qingque_resource_client.search(name, limit=1)
        if not matches:
            raise RuntimeError("青雀文档中没有找到匹配资源")
        resource_data = matches[0].__dict__
        _update_item(
            task_id,
            index,
            progress=18,
            message=f"已匹配资源：{resource_data.get('drama_name') or name}",
            resource=resource_data,
        )

    project_id = int(checkpoint.get("project_id") or 0)
    if not project_id:
        with _timed_stage(task_id, index, "create_project", "创建项目"):
            project = create_project(ProjectCreate(name=name, description="自动发布流程创建", status="active"))
            project_id = int(project["id"])
        _update_item(task_id, index, progress=25, message="项目已创建", project_id=project_id)
    destination_dir = get_settings().input_dir / f"project_{project_id}"

    downloaded = checkpoint.get("downloaded") or []
    downloaded_paths = [item.get("local_path", "") for item in downloaded]
    if not downloaded_paths or not all(Path(path).is_file() for path in downloaded_paths):
        _update_item(task_id, index, progress=25, message="正在转存并下载剧情前五集", project_id=project_id)
        with _timed_stage(task_id, index, "baidu_transfer_download", "百度转存下载"):
            download_result = download_first_episodes_from_baidupcs_share(
                resource_data.get("baidu_url", ""),
                resource_data.get("extract_code", ""),
                destination_dir,
                limit=payload.episode_limit,
                remote_name=name,
                drama_name=name,
            )
        downloaded = download_result.get("downloaded") or []
        downloaded_paths = [item["local_path"] for item in downloaded]
        _update_item(task_id, index, downloaded=downloaded)
    else:
        _update_item(task_id, index, status="running", progress=42, message="已复用下载文件")
    if not downloaded_paths:
        raise RuntimeError("没有下载到可用剧情视频")

    from .main import scan_videos, _video_ids_for_paths

    video_ids = [int(value) for value in checkpoint.get("video_ids") or []]
    scan_data: dict[str, Any] = {}
    if not video_ids:
        _update_item(task_id, index, progress=42, message="下载完成，正在扫描入库", downloaded=downloaded)
        with _timed_stage(task_id, index, "scan_import", "扫描入库"):
            scan = scan_videos(project_id=project_id)
            scan_data = scan.model_dump()
            video_ids = _video_ids_for_paths(project_id, downloaded_paths)
        _update_item(task_id, index, video_ids=video_ids, scan=scan_data)
    else:
        _update_item(task_id, index, status="running", progress=55, message="已复用扫描结果")
    if not video_ids:
        raise RuntimeError("下载完成，但没有匹配到入库视频")

    file_paths = [path for path in checkpoint.get("asset_paths") or [] if Path(path).is_file()]
    assets: list[dict[str, Any]] = [{"output_path": path} for path in file_paths]
    if file_paths:
        _update_item(task_id, index, status="running", progress=82, message="已复用剪辑产物", asset_paths=file_paths)
    elif payload.pipeline_template_key == "episode_concat_visual":
        _update_item(task_id, index, progress=55, message="正在裁剪每集首尾并随机抽取参考画面", video_ids=video_ids, scan=scan_data)
        with _timed_stage(task_id, index, "deterministic_compose", "裁剪拼接与片头片尾生成"):
            asset = compose_episode_publish_video(
                project_id=project_id,
                drama_name=name,
                source_paths=downloaded_paths,
            )
            assets = [asset]
        run_ids: list[int] = []
        file_paths = [asset["output_path"] for asset in assets if asset.get("output_path") and Path(asset["output_path"]).is_file()]
        _update_item(task_id, index, progress=75, message="确定性成片已生成", pipeline_run_ids=run_ids, asset_paths=file_paths)
    else:
        _update_item(task_id, index, progress=55, message="正在创建剪辑任务", video_ids=video_ids, scan=scan.model_dump())
        with _timed_stage(task_id, index, "create_pipeline_runs", "创建剪辑任务"):
            pipeline_result = create_pipeline_runs(
                project_id,
                PipelineRunCreate(template_key=payload.pipeline_template_key, source_video_ids=video_ids),
                enqueue=True,
            )
            run_ids = [int(run["id"]) for run in pipeline_result.get("runs") or []]
        _update_item(task_id, index, progress=65, message="剪辑任务已创建，等待生成完成", pipeline_run_ids=run_ids)
        with _timed_stage(task_id, index, "clip_generation", "剪辑生成"):
            _run_pipeline_until_done(run_ids)
            assets = _generated_assets_for_runs(run_ids, project_id)
        file_paths = [asset["output_path"] for asset in assets if asset.get("output_path") and Path(asset["output_path"]).is_file()]
        _update_item(task_id, index, progress=75, message="剪辑产物已生成", asset_paths=file_paths)
    if not file_paths:
        raise RuntimeError("剪辑完成，但没有找到可发布的视频产物")

    publish_task = None
    if payload.publish_enabled:
        if not payload.account_ids:
            raise RuntimeError("已开启发布，但没有选择发布账号")
        _update_item(task_id, index, progress=82, message="正在提交发布任务", asset_paths=file_paths)
        with _timed_stage(task_id, index, "publish", "发布"):
            publish_task = _create_publish_task(payload, title=name, file_paths=file_paths)
            _wait_publish_task(payload.publish_base_url, publish_task.get("id"))
        total_seconds = round(time.monotonic() - item_started_at, 2)
        _record_total_duration(task_id, index, total_seconds)
        _record_published(name, project_id, task_id, publish_task.get("id", ""), "发布完成", {"resource": resource_data, "assets": assets})
        _update_item(task_id, index, status="succeeded", progress=100, message=f"发布完成，总耗时 {_format_duration(total_seconds)}", publish_task=publish_task)
    else:
        total_seconds = round(time.monotonic() - item_started_at, 2)
        _record_total_duration(task_id, index, total_seconds)
        _record_published(name, project_id, task_id, "", "剪辑完成，待发布", {"resource": resource_data, "assets": assets})
        _update_item(task_id, index, status="succeeded", progress=100, message=f"剪辑完成，待发布，总耗时 {_format_duration(total_seconds)}", asset_paths=file_paths)


@contextmanager
def _timed_stage(task_id: str, index: int, key: str, label: str):
    started = time.monotonic()
    try:
        yield
    finally:
        duration = round(time.monotonic() - started, 2)
        _record_stage_duration(task_id, index, key, label, duration)


def _record_stage_duration(task_id: str, index: int, key: str, label: str, duration_seconds: float) -> None:
    with AUTO_PUBLISH_TASK_LOCK:
        task = AUTO_PUBLISH_TASKS.get(task_id)
        if not task:
            return
        items = task.get("items") or []
        if index < 0 or index >= len(items):
            return
        item = items[index]
        timings = item.setdefault("timings", {})
        timings[key] = {
            "label": label,
            "seconds": duration_seconds,
            "display": _format_duration(duration_seconds),
            "finished_at": _now_iso(),
        }
        task["logs"].append({"time": _now_iso(), "message": f"{item.get('name')}：{label}耗时 {_format_duration(duration_seconds)}"})
    _persist_task(task_id)


def _record_total_duration(task_id: str, index: int, duration_seconds: float) -> None:
    with AUTO_PUBLISH_TASK_LOCK:
        task = AUTO_PUBLISH_TASKS.get(task_id)
        if not task:
            return
        items = task.get("items") or []
        if index < 0 or index >= len(items):
            return
        item = items[index]
        item["duration_seconds"] = duration_seconds
        item["duration_display"] = _format_duration(duration_seconds)
    _persist_task(task_id)


def _format_duration(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}小时{minutes}分{secs}秒"
    if minutes:
        return f"{minutes}分{secs}秒"
    return f"{secs}秒"


def _run_pipeline_until_done(run_ids: list[int], timeout_seconds: int = 3600) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        runs = [get_pipeline_run(run_id) for run_id in run_ids]
        if all(run["status"] == "succeeded" for run in runs):
            return
        failed = [run for run in runs if run["status"] == "failed"]
        if failed:
            raise RuntimeError(f"剪辑任务失败：{failed[0].get('error') or failed[0].get('current_step')}")
        run_next_pipeline_job(worker_id=f"auto-publish-{int(time.time())}")
        time.sleep(1)
    raise RuntimeError("等待剪辑任务完成超时")


def _generated_assets_for_runs(run_ids: list[int], project_id: int) -> list[dict[str, Any]]:
    assets: list[dict[str, Any]] = []
    for run_id in run_ids:
        assets.extend(list_pipeline_generated_assets(run_id, project_id=project_id))
    assets.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return assets


def _create_publish_task(payload: AutoPublishCreate, *, title: str, file_paths: list[str]) -> dict[str, Any]:
    topics = [topic for topic in payload.topics if str(topic).strip()]
    for topic in reversed(DEFAULT_AUTO_PUBLISH_TOPICS):
        if topic not in topics:
            topics.insert(0, topic)
    body: dict[str, Any] = {
        "platform": payload.platform,
        "accountIds": payload.account_ids,
        "filePaths": file_paths,
        "title": title,
        "description": title,
        "topics": topics,
        "isOriginal": payload.is_original,
        "scheduleAt": payload.schedule_at or None,
    }
    if payload.platform == "kuaishou":
        body["kuaishouEnablePromotionTask"] = payload.kuaishou_enable_promotion_task
        if payload.kuaishou_enable_promotion_task:
            body["kuaishouPromotionTaskTitle"] = title
    response = httpx.post(
        f"{payload.publish_base_url.rstrip('/')}/api/publish/video",
        json=body,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def _wait_publish_task(base_url: str, publish_task_id: str | None, timeout_seconds: int = 7200) -> None:
    if not publish_task_id:
        raise RuntimeError("发布服务没有返回任务 ID")
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        response = httpx.get(f"{base_url.rstrip('/')}/api/tasks", timeout=15)
        response.raise_for_status()
        tasks = response.json()
        task = next((item for item in tasks if item.get("id") == publish_task_id), None)
        if task and task.get("status") == "succeeded":
            return
        if task and task.get("status") == "failed":
            raise RuntimeError(task.get("message") or "发布失败")
        time.sleep(5)
    raise RuntimeError("等待发布任务完成超时")


def _record_published(name: str, project_id: int, task_id: str, publish_task_id: str, message: str, metadata: dict[str, Any]) -> None:
    normalized = normalize_drama_name(name)
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO auto_publish_records
                (drama_name, normalized_name, status, project_id, auto_task_id, publish_task_id, message, metadata_json)
            VALUES (?, ?, 'published', ?, ?, ?, ?, ?)
            ON CONFLICT(normalized_name) DO UPDATE SET
                drama_name = excluded.drama_name,
                status = excluded.status,
                project_id = excluded.project_id,
                auto_task_id = excluded.auto_task_id,
                publish_task_id = excluded.publish_task_id,
                message = excluded.message,
                metadata_json = excluded.metadata_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (name, normalized, project_id, task_id, publish_task_id, message, json.dumps(metadata, ensure_ascii=False, default=str)),
        )


def _normalize_record(row: dict[str, Any]) -> dict[str, Any]:
    metadata = {}
    try:
        metadata = json.loads(row.get("metadata_json") or "{}")
    except json.JSONDecodeError:
        metadata = {}
    row["metadata"] = metadata
    row.pop("metadata_json", None)
    return row


def _initial_item(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "status": "pending",
        "progress": 0,
        "message": "等待处理",
        "error": "",
        "timings": {},
        "duration_seconds": 0,
        "duration_display": "",
    }


def _item_checkpoint(task_id: str, index: int) -> dict[str, Any]:
    with AUTO_PUBLISH_TASK_LOCK:
        task = AUTO_PUBLISH_TASKS.get(task_id) or {}
        items = task.get("items") or []
        if index < 0 or index >= len(items):
            return {}
        return json.loads(json.dumps(items[index], ensure_ascii=False, default=str))


def _update_task_progress(task_id: str) -> None:
    task = get_auto_publish_task(task_id)
    items = task.get("items") or []
    if not items:
        return
    completed = len([item for item in items if item.get("status") in {"succeeded", "failed", "skipped"}])
    average = sum(int(item.get("progress") or 0) for item in items) // len(items)
    _update_task(task_id, completed=completed, progress=average, message=f"已处理 {completed}/{len(items)}")


def _update_task(task_id: str, **changes: Any) -> None:
    with AUTO_PUBLISH_TASK_LOCK:
        task = AUTO_PUBLISH_TASKS.get(task_id)
        if not task:
            return
        task.update(changes)
    _persist_task(task_id)


def _update_item(task_id: str, index: int, **changes: Any) -> None:
    with AUTO_PUBLISH_TASK_LOCK:
        task = AUTO_PUBLISH_TASKS.get(task_id)
        if not task:
            return
        items = task.get("items") or []
        if index < 0 or index >= len(items):
            return
        items[index].update(changes)
        task["logs"].append({"time": _now_iso(), "message": f"{items[index].get('name')}：{changes.get('message', '')}"})
    _persist_task(task_id)


def _persist_task(task_id: str) -> None:
    with AUTO_PUBLISH_TASK_LOCK:
        task = AUTO_PUBLISH_TASKS.get(task_id)
        payload = AUTO_PUBLISH_PAYLOADS.get(task_id)
        if not task or not payload:
            return
        task_json = json.dumps(task, ensure_ascii=False, default=str)
        payload_json = json.dumps(payload.model_dump(mode="json"), ensure_ascii=False)
    with connect() as conn:
        _ensure_task_store(conn)
        conn.execute(
            """
            INSERT INTO auto_publish_tasks (id, payload_json, task_json)
            VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                payload_json = excluded.payload_json,
                task_json = excluded.task_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (task_id, payload_json, task_json),
        )


def _restore_task(task_id: str) -> dict[str, Any]:
    with connect() as conn:
        _ensure_task_store(conn)
        row = conn.execute(
            "SELECT payload_json, task_json FROM auto_publish_tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
    if not row:
        return {}
    try:
        task = json.loads(row["task_json"])
        payload = AutoPublishCreate.model_validate_json(row["payload_json"])
    except (json.JSONDecodeError, ValueError):
        return {}
    with AUTO_PUBLISH_TASK_LOCK:
        AUTO_PUBLISH_TASKS[task_id] = task
        AUTO_PUBLISH_PAYLOADS[task_id] = payload
    return json.loads(json.dumps(task, ensure_ascii=False, default=str))


def _ensure_task_store(conn: Any) -> None:
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


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")
