from __future__ import annotations

import json
from datetime import datetime
from threading import Lock
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Optional

import httpx
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse

from .ai_clients import (
    generate_image_from_prompt,
    generate_promotion_content,
    generate_short_drama_template_visual,
    gemini_plan_short_drama_template_visual,
    image_task_filename,
)
from .ai_pipeline import enrich_suggestions_with_ai
from .baidu_pcs import BaiduPCSError, download_first_episodes_from_baidupcs_share
from .config import BASE_DIR, get_settings
from .db import connect, init_db, rows_to_dicts
from .auto_publish import (
    create_auto_publish_task,
    execute_auto_publish_task,
    execute_auto_publish_retry,
    get_auto_publish_record,
    get_auto_publish_task,
    list_auto_publish_records,
    retry_auto_publish_item,
)
from .ffmpeg import (
    cut_clip,
    concat_video_segments,
    discover_videos,
    format_time,
    parse_time,
    probe_video,
    render_clip_segment,
    render_image_segment,
    render_text_card,
    suggest_audio_peak_clips,
)
from .intro_templates import (
    create_intro_template,
    delete_intro_template,
    get_intro_template,
    list_intro_templates,
    update_intro_template,
)
from .models import (
    ClipCreate,
    AutoPublishCreate,
    ContentPromotionGenerate,
    IntroTemplateCreate,
    IntroTemplateUpdate,
    IntroTemplateVisualGenerate,
    IntroWorkflowRunCreate,
    PipelineRunCreate,
    ProjectCreate,
    ProjectUpdate,
    PromptConfigCreate,
    PromptConfigUpdate,
    QingqueResourceMatch,
    ResourceImportCreate,
    ScanResult,
)
from .pipeline import (
    cancel_pipeline_run,
    create_and_execute_pipeline_runs,
    create_pipeline_runs,
    get_pipeline_run,
    get_pipeline_template,
    list_pipeline_jobs,
    list_pipeline_artifacts,
    list_pipeline_generated_assets,
    list_pipeline_runs,
    list_pipeline_steps,
    list_pipeline_templates,
    run_next_pipeline_job,
)
from .promo_pipeline import PROMO_VARIANTS, generate_promo_video
from .projects import (
    create_project,
    delete_project,
    get_project,
    list_project_assets,
    list_projects,
    record_generated_asset,
    resolve_project_id,
    update_project,
)
from .prompts import (
    create_prompt_config,
    delete_prompt_config,
    get_prompt_config,
    list_prompt_configs,
    update_prompt_config,
)
from .qingque_resource import QingqueResourceError, qingque_resource_client


app = FastAPI(title="Highlight Service", version="0.1.0")
WORKFLOW_TASKS: dict[str, dict] = {}
WORKFLOW_TASK_LOCK = Lock()
RESOURCE_IMPORT_TASKS: dict[str, dict] = {}
RESOURCE_IMPORT_TASK_LOCK = Lock()


@app.on_event("startup")
def startup() -> None:
    init_db()
    settings = get_settings()
    settings.input_dir.mkdir(parents=True, exist_ok=True)
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    settings.promo_dir.mkdir(parents=True, exist_ok=True)
    settings.work_dir.mkdir(parents=True, exist_ok=True)
    settings.reports_dir.mkdir(parents=True, exist_ok=True)
    settings.intro_template_asset_dir.mkdir(parents=True, exist_ok=True)
    settings.workflow_dir.mkdir(parents=True, exist_ok=True)


@app.get("/")
def index() -> dict:
    return {
        "ok": True,
        "service": "highlight-service",
        "docs": "/docs",
        "health": "/api/health",
    }


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=204)


@app.get("/api/health")
def health() -> dict:
    settings = get_settings()
    return {
        "ok": True,
        "input_dir": str(settings.input_dir),
        "output_dir": str(settings.output_dir),
        "openai": {
            "api_key_configured": bool(settings.openai_api_key),
            "base_url_configured": bool(settings.openai_base_url),
            "text_model": settings.openai_text_model,
            "image_model": settings.openai_image_model,
            "wire_api": settings.openai_wire_api,
            "transcribe_model": settings.openai_transcribe_model,
            "transcribe_provider": settings.transcribe_provider,
        },
        "gemini": {
            "api_key_configured": bool(settings.gemini_api_key),
            "base_url_configured": bool(settings.google_gemini_base_url or settings.gemini_base_url),
            "model": settings.gemini_model,
            "api_style": settings.gemini_api_style,
        },
    }


@app.get("/api/projects")
def api_list_projects() -> list[dict]:
    return list_projects()


@app.post("/api/projects")
def api_create_project(payload: ProjectCreate) -> dict:
    return create_project(payload)


@app.get("/api/projects/{project_id}")
def api_get_project(project_id: int) -> dict:
    return get_project(project_id)


@app.put("/api/projects/{project_id}")
def api_update_project(project_id: int, payload: ProjectUpdate) -> dict:
    return update_project(project_id, payload)


@app.delete("/api/projects/{project_id}")
def api_delete_project(project_id: int) -> dict:
    return delete_project(project_id)


@app.get("/api/projects/{project_id}/assets")
def api_list_project_assets(project_id: int) -> list[dict]:
    return list_project_assets(project_id)


@app.get("/api/pipeline-templates")
def api_list_pipeline_templates() -> list[dict]:
    return list_pipeline_templates()


@app.get("/api/pipeline-templates/{template_key}")
def api_get_pipeline_template(template_key: str) -> dict:
    return get_pipeline_template(template_key)


@app.post("/api/projects/{project_id}/pipeline-runs")
def api_create_pipeline_runs(project_id: int, payload: PipelineRunCreate, enqueue: bool = False) -> dict:
    get_project(project_id)
    template = get_pipeline_template(payload.template_key)
    if enqueue or template.get("run_strategy") == "aggregate":
        return create_pipeline_runs(project_id, payload, enqueue=True)
    return create_and_execute_pipeline_runs(project_id, payload)


@app.get("/api/projects/{project_id}/pipeline-runs")
def api_list_pipeline_runs(project_id: int) -> list[dict]:
    get_project(project_id)
    return list_pipeline_runs(project_id)


@app.get("/api/pipeline-runs/{run_id}/steps")
def api_list_pipeline_steps(run_id: int, project_id: Optional[int] = None) -> list[dict]:
    return list_pipeline_steps(run_id, project_id=project_id)


@app.get("/api/pipeline-runs/{run_id}/artifacts")
def api_list_pipeline_artifacts(run_id: int, project_id: Optional[int] = None) -> list[dict]:
    return list_pipeline_artifacts(run_id, project_id=project_id)


@app.get("/api/pipeline-runs/{run_id}/generated-assets")
def api_list_pipeline_generated_assets(run_id: int, project_id: Optional[int] = None) -> list[dict]:
    return list_pipeline_generated_assets(run_id, project_id=project_id)


@app.post("/api/pipeline-runs/{run_id}/cancel")
def api_cancel_pipeline_run(run_id: int, project_id: Optional[int] = None) -> dict:
    return cancel_pipeline_run(run_id, project_id=project_id)


@app.get("/api/pipeline-jobs")
def api_list_pipeline_jobs(status: Optional[str] = None) -> list[dict]:
    return list_pipeline_jobs(status=status)


@app.post("/api/pipeline-jobs/run-next")
def api_run_next_pipeline_job() -> dict:
    return run_next_pipeline_job()


@app.get("/api/pipeline-runs/{run_id}")
def api_get_pipeline_run(run_id: int, project_id: Optional[int] = None) -> dict:
    return get_pipeline_run(run_id, project_id=project_id)


@app.post("/api/upload")
async def upload_videos(files: list[UploadFile], project_id: Optional[int] = None) -> dict:
    settings = get_settings()
    resolved_project_id = resolve_project_id(project_id)
    upload_dir = settings.input_dir / f"project_{resolved_project_id}"
    upload_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for file in files:
        if not file.filename:
            continue
        suffix = Path(file.filename).suffix.lower()
        if suffix not in {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"}:
            raise HTTPException(status_code=400, detail=f"unsupported file type: {file.filename}")
        target = _unique_path(upload_dir / Path(file.filename).name)
        with target.open("wb") as handle:
            while chunk := await file.read(1024 * 1024):
                handle.write(chunk)
        saved.append(str(target))
    return {"saved": saved}


@app.post("/api/scan", response_model=ScanResult)
def scan_videos(project_id: Optional[int] = None) -> ScanResult:
    settings = get_settings()
    resolved_project_id = resolve_project_id(project_id)
    indexed = 0
    failed: list[str] = []
    scan_dir = settings.input_dir / f"project_{resolved_project_id}"
    legacy_scan = project_id is None
    paths = discover_videos(settings.input_dir if legacy_scan else scan_dir)
    for path in paths:
        try:
            row_project_id = _project_id_for_scanned_path(path, resolved_project_id, settings.input_dir, legacy_scan)
            info = probe_video(path)
            stat = path.stat()
            with connect() as conn:
                conn.execute(
                    """
                    INSERT INTO videos
                        (project_id, path, name, size_bytes, duration, width, height, fps, codec, updated_at)
                    VALUES
                        (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(path) DO UPDATE SET
                        project_id=excluded.project_id,
                        name=excluded.name,
                        size_bytes=excluded.size_bytes,
                        duration=excluded.duration,
                        width=excluded.width,
                        height=excluded.height,
                        fps=excluded.fps,
                        codec=excluded.codec,
                        updated_at=CURRENT_TIMESTAMP
                    """,
                    (
                        row_project_id,
                        str(path),
                        path.name,
                        stat.st_size,
                        info["duration"],
                        info["width"],
                        info["height"],
                        info["fps"],
                        info["codec"],
                    ),
                )
            indexed += 1
        except Exception as exc:  # noqa: BLE001 - return per-file scan failures to the UI.
            failed.append(f"{path.name}: {exc}")
    return ScanResult(indexed=indexed, failed=failed)


@app.post("/api/resource-imports")
def create_resource_import(payload: ResourceImportCreate, background_tasks: BackgroundTasks) -> dict:
    project = get_project(payload.project_id)
    task_id = uuid.uuid4().hex
    with RESOURCE_IMPORT_TASK_LOCK:
        RESOURCE_IMPORT_TASKS[task_id] = {
            "id": task_id,
            "status": "pending",
            "progress": 0,
            "message": "资源导入任务已创建",
            "project_id": payload.project_id,
            "project_name": project["name"],
            "baidu_url": payload.baidu_url,
            "extract_code": payload.extract_code,
            "drama_name": payload.drama_name,
            "episode_limit": payload.episode_limit,
            "pipeline_template_key": payload.pipeline_template_key,
            "downloaded": [],
            "selected": [],
            "scan": None,
            "video_ids": [],
            "pipeline_runs": [],
            "error": "",
            "logs": [],
            "created_at": _now_iso(),
            "started_at": None,
            "finished_at": None,
        }
    _append_resource_import_log(task_id, "任务已提交到后台")
    background_tasks.add_task(_execute_resource_import_task, task_id, payload)
    return _get_resource_import_task(task_id)


@app.get("/api/resource-imports/{task_id}")
def get_resource_import(task_id: str) -> dict:
    return _get_resource_import_task(task_id)


@app.get("/api/qingque/resources/search", response_model=list[QingqueResourceMatch])
def search_qingque_resources(
    name: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=50),
    refresh: bool = False,
) -> list[QingqueResourceMatch]:
    try:
        matches = qingque_resource_client.search(name, limit=limit, refresh=refresh)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"青雀文档请求失败：{exc}") from exc
    except QingqueResourceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return [QingqueResourceMatch(**item.__dict__) for item in matches]


@app.post("/api/auto-publish/tasks")
def create_auto_publish(payload: AutoPublishCreate, background_tasks: BackgroundTasks) -> dict:
    task_id = uuid.uuid4().hex
    task = create_auto_publish_task(task_id, payload)
    background_tasks.add_task(execute_auto_publish_task, task_id, payload)
    return task


@app.get("/api/auto-publish/tasks/{task_id}")
def get_auto_publish(task_id: str) -> dict:
    task = get_auto_publish_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="auto publish task not found")
    return task


@app.post("/api/auto-publish/tasks/{task_id}/items/{item_index}/retry")
def retry_auto_publish(task_id: str, item_index: int, background_tasks: BackgroundTasks) -> dict:
    try:
        task = retry_auto_publish_item(task_id, item_index)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except IndexError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    background_tasks.add_task(execute_auto_publish_retry, task_id, item_index)
    return task


@app.get("/api/auto-publish/records")
def api_list_auto_publish_records() -> list[dict]:
    return list_auto_publish_records()


@app.get("/api/auto-publish/records/check")
def api_check_auto_publish_record(name: str = Query(..., min_length=1)) -> dict:
    record = get_auto_publish_record(name)
    return {"exists": bool(record), "record": record}


def _project_id_for_scanned_path(path: Path, fallback_project_id: int, input_dir: Path, legacy_scan: bool) -> int:
    if not legacy_scan:
        return fallback_project_id
    try:
        relative = path.resolve().relative_to(input_dir.resolve())
    except ValueError:
        return fallback_project_id
    first_part = relative.parts[0] if relative.parts else ""
    if first_part.startswith("project_"):
        try:
            project_id = int(first_part.replace("project_", "", 1))
            get_project(project_id)
            return project_id
        except Exception:
            return fallback_project_id
    return fallback_project_id


@app.get("/api/videos")
def list_videos(project_id: Optional[int] = None) -> list[dict]:
    resolved_project_id = resolve_project_id(project_id)
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM videos WHERE project_id = ? ORDER BY updated_at DESC, id DESC",
            (resolved_project_id,),
        ).fetchall()
    return rows_to_dicts(rows)


@app.get("/api/prompts")
def list_prompts(category: Optional[str] = None) -> list[dict]:
    return list_prompt_configs(category=category)


@app.post("/api/prompts")
def create_prompt(payload: PromptConfigCreate) -> dict:
    return create_prompt_config(payload)


@app.get("/api/prompts/{prompt_id}")
def get_prompt(prompt_id: int) -> dict:
    return get_prompt_config(prompt_id)


@app.put("/api/prompts/{prompt_id}")
def update_prompt(prompt_id: int, payload: PromptConfigUpdate) -> dict:
    return update_prompt_config(prompt_id, payload)


@app.delete("/api/prompts/{prompt_id}")
def delete_prompt(prompt_id: int) -> dict:
    return delete_prompt_config(prompt_id)


@app.get("/api/intro-templates")
def api_list_intro_templates() -> list[dict]:
    return list_intro_templates()


@app.post("/api/intro-templates")
def api_create_intro_template(payload: IntroTemplateCreate) -> dict:
    return create_intro_template(payload)


@app.post("/api/intro-template-assets")
async def upload_intro_template_asset(file: UploadFile = File(...)) -> dict:
    if not file.filename:
        raise HTTPException(status_code=400, detail="filename is required")
    content_type = (file.content_type or "").lower()
    suffix = Path(file.filename).suffix.lower()
    allowed_suffixes = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    if suffix not in allowed_suffixes or not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail=f"unsupported image type: {file.filename}")

    settings = get_settings()
    settings.intro_template_asset_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{suffix}"
    target = settings.intro_template_asset_dir / filename
    with target.open("wb") as handle:
        while chunk := await file.read(1024 * 1024):
            handle.write(chunk)
    return {
        "filename": filename,
        "path": str(target),
        "url": f"/api/intro-template-assets/{filename}",
    }


@app.get("/api/intro-template-assets/{filename}", include_in_schema=False)
def get_intro_template_asset(filename: str) -> FileResponse:
    if Path(filename).name != filename:
        raise HTTPException(status_code=400, detail="invalid filename")
    path = get_settings().intro_template_asset_dir / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="asset not found")
    media_type = "video/mp4" if path.suffix.lower() == ".mp4" else None
    return FileResponse(path, media_type=media_type)


@app.get("/api/content-promotion/assets/{filename}", include_in_schema=False)
def get_content_promotion_asset(filename: str) -> FileResponse:
    if Path(filename).name != filename:
        raise HTTPException(status_code=400, detail="invalid filename")
    path = get_settings().content_promotion_asset_dir / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="asset not found")
    return FileResponse(path)


@app.post("/api/content-promotion/generate")
def generate_content_promotion(payload: ContentPromotionGenerate) -> dict:
    content = generate_promotion_content(
        payload.description,
        payload.audience,
        payload.tone,
        payload.platform,
    )
    if not content.get("ok"):
        raise HTTPException(status_code=502, detail=content)
    settings = get_settings()
    filename = f"promotion_{uuid.uuid4().hex}.png"
    output_path = settings.content_promotion_asset_dir / filename
    image = generate_image_from_prompt(
        content["image_prompt"],
        output_path,
        image_model=settings.openai_image_model,
    )
    if not image.get("ok"):
        raise HTTPException(status_code=502, detail={"message": "推广文案已生成，但宣传图生成失败", "content": content, "image": image})
    return {
        "title": content["title"],
        "content": content["content"],
        "topics": content["topics"],
        "strategy": content.get("strategy") or "",
        "image_prompt": content["image_prompt"],
        "image_path": str(output_path),
        "image_url": f"/api/content-promotion/assets/{filename}",
        "image_result": image,
    }


@app.post("/api/intro-templates/visuals/generate")
def generate_intro_template_visual(payload: IntroTemplateVisualGenerate) -> dict:
    settings = get_settings()
    output_filename = image_task_filename(payload.kind, payload.drama_name)
    output_path = settings.intro_template_asset_dir / output_filename
    reference_path = Path(payload.reference_image_path) if payload.reference_image_path else None
    gemini_strategy = gemini_plan_short_drama_template_visual(
        kind=payload.kind,
        drama_name=payload.drama_name,
        style=payload.style,
        brief=payload.brief,
        duration=payload.duration,
    )
    result = generate_short_drama_template_visual(
        kind=payload.kind,
        drama_name=payload.drama_name,
        style=payload.style,
        brief=payload.brief,
        duration=payload.duration,
        output_path=output_path,
        reference_image_path=reference_path,
        gemini_strategy=gemini_strategy,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=502, detail=result)

    url = f"/api/intro-template-assets/{output_filename}"
    video_filename = f"{output_path.stem}.mp4"
    video_path = settings.intro_template_asset_dir / video_filename
    render_image_segment(output_path, video_path, payload.duration)
    result["url"] = url
    result["path"] = str(output_path)
    result["video_url"] = f"/api/intro-template-assets/{video_filename}"
    result["video_path"] = str(video_path)
    result["orchestration"] = {
        "gemini": gemini_strategy,
        "gpt": {
            "provider": "openai-compatible",
            "model": settings.openai_image_model,
            "role": "image_generation",
        },
        "video": {
            "mode": "ffmpeg_image_segment",
            "duration": payload.duration,
            "output_path": str(video_path),
        },
    }
    if payload.template_id:
        field_prefix = "intro" if payload.kind == "intro" else "outro"
        template = update_intro_template(
            payload.template_id,
            IntroTemplateUpdate(
                **{
                    f"{field_prefix}_image_path": str(output_path),
                    f"{field_prefix}_image_url": url,
                }
            ),
        )
        result["template"] = template
    return result


@app.get("/api/intro-templates/{template_id}")
def api_get_intro_template(template_id: int) -> dict:
    return get_intro_template(template_id)


@app.put("/api/intro-templates/{template_id}")
def api_update_intro_template(template_id: int, payload: IntroTemplateUpdate) -> dict:
    return update_intro_template(template_id, payload)


@app.delete("/api/intro-templates/{template_id}")
def api_delete_intro_template(template_id: int) -> dict:
    return delete_intro_template(template_id)


@app.post("/api/intro-workflow/run")
def run_intro_workflow(payload: IntroWorkflowRunCreate, background_tasks: BackgroundTasks) -> dict:
    template = get_intro_template(payload.template_id)
    if not payload.source_video_ids:
        raise HTTPException(status_code=400, detail="source_video_ids is required")
    task_id = uuid.uuid4().hex
    with WORKFLOW_TASK_LOCK:
        WORKFLOW_TASKS[task_id] = {
            "id": task_id,
            "status": "pending",
            "progress": 0,
            "message": "任务已创建，等待后端开始处理",
            "template_id": template["id"],
            "template_name": template["name"],
            "source_video_ids": payload.source_video_ids,
            "generated": [],
            "failed": [],
            "logs": [],
            "created_at": _now_iso(),
            "started_at": None,
            "finished_at": None,
        }
    _append_workflow_task_log(task_id, "任务已提交到后台队列")
    background_tasks.add_task(_execute_intro_workflow_task, task_id, payload, template)
    return _get_workflow_task(task_id)


@app.get("/api/intro-workflow/tasks/{task_id}")
def get_intro_workflow_task(task_id: str) -> dict:
    return _get_workflow_task(task_id)


def _execute_intro_workflow_task(task_id: str, payload: IntroWorkflowRunCreate, template: dict) -> None:
    settings = get_settings()
    project_id = resolve_project_id(None)
    output_root = settings.workflow_dir / f"template_{template['id']}"
    work_dir = output_root / "work"
    final_dir = output_root / "final"
    work_dir.mkdir(parents=True, exist_ok=True)
    final_dir.mkdir(parents=True, exist_ok=True)
    generated = []
    failed = []
    total = len(payload.source_video_ids)
    _update_workflow_task(task_id, status="running", progress=1, started_at=_now_iso(), message="后台任务已开始")
    for index, video_id in enumerate(payload.source_video_ids, start=1):
        base_progress = int((index - 1) / max(total, 1) * 100)
        try:
            _update_workflow_task(task_id, progress=max(base_progress, 1), message=f"正在处理第 {index}/{total} 个视频")
            video = _get_video(video_id)
            video_project_id = int(video.get("project_id") or project_id)
            source = Path(video["path"])
            if not source.exists():
                raise FileNotFoundError(str(source))
            safe_stem = source.stem.replace("/", "_").replace(" ", "_")
            duration = float(template.get("duration") or 3)
            _append_workflow_task_log(task_id, f"开始处理：{video['name']}")
            intro_segment = work_dir / f"{safe_stem}_intro.mp4"
            intro_image = Path(template.get("intro_image_path") or "")
            _update_workflow_task(task_id, progress=min(base_progress + 8, 95), message=f"正在生成片头：{video['name']}")
            if intro_image.exists():
                render_image_segment(intro_image, intro_segment, duration)
                _append_workflow_task_log(task_id, f"片头已生成：{intro_segment.name}")
            else:
                render_text_card(
                    intro_segment,
                    template.get("name") or "固定片头",
                    template.get("summary") or template.get("style") or "",
                    duration_seconds=duration,
                )
                _append_workflow_task_log(task_id, f"片头图缺失，已使用文字片头兜底：{intro_segment.name}")
            outro_segment = work_dir / f"{safe_stem}_outro.mp4"
            outro_image = Path(template.get("outro_image_path") or "")
            _update_workflow_task(task_id, progress=min(base_progress + 18, 95), message=f"正在生成片尾：{video['name']}")
            if outro_image.exists():
                render_image_segment(outro_image, outro_segment, duration)
                _append_workflow_task_log(task_id, f"片尾已生成：{outro_segment.name}")
            else:
                render_text_card(
                    outro_segment,
                    template.get("drama_name") or template.get("name") or "固定片尾",
                    "下集更精彩",
                    duration_seconds=duration,
                )
                _append_workflow_task_log(task_id, f"片尾图缺失，已使用文字片尾兜底：{outro_segment.name}")
            body_segment = work_dir / f"{safe_stem}_body.mp4"
            video_duration = float(video.get("duration") or 0)
            if video_duration <= 0:
                info = probe_video(source)
                video_duration = float(info.get("duration") or 0)
            _update_workflow_task(task_id, progress=min(base_progress + 42, 96), message=f"正在转码正片：{video['name']}")
            render_clip_segment(source, body_segment, 0, video_duration)
            _append_workflow_task_log(task_id, f"正片转码完成：{body_segment.name}")
            output = final_dir / f"{safe_stem}_with_intro_outro.mp4"
            _update_workflow_task(task_id, progress=min(base_progress + 74, 98), message=f"正在拼接产物：{video['name']}")
            concat_video_segments([intro_segment, body_segment, outro_segment], output)
            asset = record_generated_asset(
                project_id=video_project_id,
                source_video_id=video_id,
                asset_type="workflow_intro_outro",
                title=f"{video['name']} 片头片尾版",
                description=f"使用模板：{template['name']}",
                output_path=output,
                download_url=f"/api/workflow-assets/{output.name}/download",
                duration=video_duration + duration * 2,
                metadata={
                    "template_id": template["id"],
                    "template_name": template["name"],
                    "intro_duration": duration,
                    "outro_duration": duration,
                    "source_duration": video_duration,
                    "intro_image_path": template.get("intro_image_path") or "",
                    "outro_image_path": template.get("outro_image_path") or "",
                },
            )
            generated.append(asset)
            _append_workflow_task_log(task_id, f"产物已生成：{output.name}")
        except Exception as exc:  # noqa: BLE001 - continue batch and report per-video failures.
            error = str(exc)
            failed.append({"video_id": video_id, "error": error})
            _append_workflow_task_log(task_id, f"处理失败：视频 ID {video_id}，{error}", level="error")
        _update_workflow_task(
            task_id,
            generated=generated,
            failed=failed,
            progress=min(int(index / max(total, 1) * 100), 99),
            message=f"已完成 {index}/{total} 个视频",
        )
    status = "succeeded" if generated and not failed else "failed" if not generated else "partial"
    _update_workflow_task(
        task_id,
        status=status,
        progress=100,
        message=f"任务完成：生成 {len(generated)} 个，失败 {len(failed)} 个",
        generated=generated,
        failed=failed,
        finished_at=_now_iso(),
    )
    _append_workflow_task_log(task_id, f"任务结束：生成 {len(generated)} 个，失败 {len(failed)} 个")


@app.get("/api/workflow-assets/{filename}/download")
def download_workflow_asset(filename: str) -> FileResponse:
    if Path(filename).name != filename:
        raise HTTPException(status_code=400, detail="invalid filename")
    matches = list(get_settings().workflow_dir.rglob(filename))
    if not matches:
        raise HTTPException(status_code=404, detail="workflow asset not found")
    return FileResponse(matches[0], media_type="video/mp4", filename=matches[0].name)


@app.delete("/api/videos")
def clear_uploaded_videos(project_id: Optional[int] = None) -> dict:
    settings = get_settings()
    resolved_project_id = resolve_project_id(project_id)
    project_input_dir = settings.input_dir / f"project_{resolved_project_id}"
    removed_files = 0
    removed_work_files = 0
    failed: list[str] = []
    for path in discover_videos(project_input_dir):
        try:
            path.unlink()
            removed_files += 1
        except Exception as exc:  # noqa: BLE001 - report file cleanup failures.
            failed.append(f"{path.name}: {exc}")

    for directory_name in ("audio", "proxy", "clips", "frames", "transcripts"):
        directory = settings.work_dir / directory_name
        if not directory.exists():
            continue
        for path in directory.rglob("*"):
            if not path.is_file():
                continue
            try:
                path.unlink()
                removed_work_files += 1
            except Exception as exc:  # noqa: BLE001 - report cleanup failures.
                failed.append(f"{path.name}: {exc}")

    with connect() as conn:
        video_rows = conn.execute("SELECT id FROM videos WHERE project_id = ?", (resolved_project_id,)).fetchall()
        video_ids = [row["id"] for row in video_rows]
        if video_ids:
            placeholders = ",".join("?" for _ in video_ids)
            conn.execute(f"DELETE FROM clips WHERE video_id IN ({placeholders})", video_ids)
        conn.execute("DELETE FROM generated_assets WHERE project_id = ?", (resolved_project_id,))
        conn.execute("DELETE FROM videos WHERE project_id = ?", (resolved_project_id,))

    return {
        "removed_files": removed_files,
        "removed_work_files": removed_work_files,
        "failed": failed,
        "outputs_preserved": str(settings.output_dir),
    }


@app.post("/api/highlights/auto")
def auto_generate_highlights(engine: str = "ai", limit: int = 0, project_id: Optional[int] = None) -> dict:
    engine = "ai"
    resolved_project_id = resolve_project_id(project_id)
    with connect() as conn:
        videos = rows_to_dicts(
            conn.execute("SELECT * FROM videos WHERE project_id = ? ORDER BY id", (resolved_project_id,)).fetchall()
        )
    if limit > 0:
        videos = videos[:limit]

    generated = []
    for video in videos:
        source = Path(video["path"])
        duration = float(video.get("duration") or 0)
        suggestions = suggest_audio_peak_clips(source, duration)
        suggestions, model_review = enrich_suggestions_with_ai(video, suggestions)
        for suggestion in suggestions:
            output = get_settings().output_dir / (
                f"{source.stem.replace(' ', '_')}_auto_{format_time(suggestion['start'])}_{format_time(suggestion['end'])}.mp4"
            )
            try:
                cut_clip(source, output, suggestion["start"], suggestion["end"])
            except Exception as exc:  # noqa: BLE001 - continue batch and report failures.
                generated.append(
                    {
                        "video_id": video["id"],
                        "video_name": video["name"],
                        "status": "failed",
                        "error": str(exc),
                        "engine": engine,
                    }
                )
                continue
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
                        f"{suggestion['reason']} | engine={engine}",
                        str(output),
                    ),
                )
                clip_id = cursor.lastrowid
            asset = record_generated_asset(
                project_id=resolved_project_id,
                source_video_id=video["id"],
                clip_id=clip_id,
                asset_type="highlight",
                title=f"{video['name']} 高光片段",
                description=suggestion.get("reason", ""),
                output_path=output,
                download_url=f"/api/clips/{clip_id}/download",
                duration=suggestion["end"] - suggestion["start"],
                metadata={"engine": engine, "suggestion": suggestion, "model_review": model_review},
            )
            generated.append(
                {
                    "asset_id": asset["id"],
                    "clip_id": clip_id,
                    "video_id": video["id"],
                    "video_name": video["name"],
                    "status": "exported",
                    "start": suggestion["start"],
                    "end": suggestion["end"],
                    "score": suggestion["score"],
                    "engine": engine,
                    "model_review": model_review,
                    "ai": suggestion.get("ai"),
                }
            )
    return {"generated": generated}


@app.post("/api/highlights/auto/stream")
def auto_generate_highlights_stream(engine: str = "ai", limit: int = 0, project_id: Optional[int] = None) -> StreamingResponse:
    return _ndjson_response(_iter_highlight_events(engine=engine, limit=limit, project_id=project_id))


@app.post("/api/promos/generate")
def generate_promo(limit: int = 3, windows_per_video: int = 2, project_id: Optional[int] = None) -> dict:
    resolved_project_id = resolve_project_id(project_id)
    with connect() as conn:
        videos = rows_to_dicts(
            conn.execute("SELECT * FROM videos WHERE project_id = ? ORDER BY id", (resolved_project_id,)).fetchall()
        )
    if not videos:
        raise HTTPException(status_code=400, detail="no uploaded videos")
    safe_limit = max(1, min(20, limit))
    safe_windows = max(1, min(4, windows_per_video))
    result = generate_promo_video(videos, limit=safe_limit, windows_per_video=safe_windows)
    assets = _record_promo_assets(resolved_project_id, result)
    if assets:
        result["asset_ids"] = [asset["id"] for asset in assets]
    return result


@app.post("/api/promos/generate/stream")
def generate_promo_stream(limit: int = 3, windows_per_video: int = 2, project_id: Optional[int] = None) -> StreamingResponse:
    return _ndjson_response(_iter_promo_events(limit=limit, windows_per_video=windows_per_video, project_id=project_id))


@app.get("/api/promos/latest/download")
def download_latest_promo() -> FileResponse:
    path = get_settings().promo_dir / "promo_latest.mp4"
    if not path.exists():
        raise HTTPException(status_code=404, detail="promo file not found")
    return FileResponse(path, media_type="video/mp4", filename=path.name)


@app.get("/api/promos/{variant_key}/download")
def download_promo_variant(variant_key: str) -> FileResponse:
    if variant_key not in PROMO_VARIANTS:
        raise HTTPException(status_code=404, detail="promo variant not found")
    path = get_settings().promo_dir / f"promo_{variant_key}.mp4"
    if not path.exists():
        raise HTTPException(status_code=404, detail="promo file not found")
    return FileResponse(path, media_type="video/mp4", filename=path.name)


@app.get("/api/promo-files/{filename}/download")
def download_promo_file(filename: str) -> FileResponse:
    if Path(filename).name != filename or not filename.endswith(".mp4"):
        raise HTTPException(status_code=400, detail="invalid promo filename")
    path = get_settings().promo_dir / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="promo file not found")
    return FileResponse(path, media_type="video/mp4", filename=path.name)


@app.get("/api/videos/{video_id}")
def get_video(video_id: int, project_id: Optional[int] = None) -> dict:
    video = _get_video(video_id)
    if project_id is not None and int(video.get("project_id") or 0) != project_id:
        raise HTTPException(status_code=404, detail="video not found in project")
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM clips WHERE video_id = ? ORDER BY created_at DESC, id DESC",
            (video_id,),
        ).fetchall()
    video["clips"] = rows_to_dicts(rows)
    return video


@app.post("/api/videos/{video_id}/clips")
def create_clip(video_id: int, payload: ClipCreate) -> dict:
    video = _get_video(video_id)
    project_id = int(video.get("project_id") or resolve_project_id(None))
    start_seconds = parse_time(payload.start)
    end_seconds = parse_time(payload.end)
    if video.get("duration") and end_seconds > float(video["duration"]) + 0.2:
        raise HTTPException(status_code=400, detail="end time exceeds video duration")

    source = Path(video["path"])
    safe_stem = source.stem.replace("/", "_").replace(" ", "_")
    output = get_settings().output_dir / (
        f"{safe_stem}_{format_time(start_seconds)}_{format_time(end_seconds)}.mp4"
    )
    try:
        cut_clip(source, output, start_seconds, end_seconds)
    except Exception as exc:  # noqa: BLE001 - surface ffmpeg failures to the UI.
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO clips
                (video_id, start_seconds, end_seconds, reason, output_path, status)
            VALUES
                (?, ?, ?, ?, ?, 'exported')
            """,
            (video_id, start_seconds, end_seconds, payload.reason, str(output)),
        )
        clip_id = cursor.lastrowid
        row = conn.execute("SELECT * FROM clips WHERE id = ?", (clip_id,)).fetchone()
    record_generated_asset(
        project_id=project_id,
        source_video_id=video_id,
        clip_id=clip_id,
        asset_type="clip",
        title=f"{video['name']} 手动片段",
        description=payload.reason,
        output_path=output,
        download_url=f"/api/clips/{clip_id}/download",
        duration=end_seconds - start_seconds,
        metadata={"start": start_seconds, "end": end_seconds, "reason": payload.reason},
    )
    return dict(row)


@app.get("/api/clips/{clip_id}/download")
def download_clip(clip_id: int) -> FileResponse:
    with connect() as conn:
        row = conn.execute("SELECT * FROM clips WHERE id = ?", (clip_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="clip not found")
    path = Path(row["output_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="clip file not found")
    return FileResponse(path, media_type="video/mp4", filename=path.name)


def _get_video(video_id: int) -> dict:
    with connect() as conn:
        row = conn.execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="video not found")
    return dict(row)


def _execute_resource_import_task(task_id: str, payload: ResourceImportCreate) -> None:
    settings = get_settings()
    destination_dir = settings.input_dir / f"project_{payload.project_id}"
    _update_resource_import_task(
        task_id,
        status="running",
        progress=5,
        started_at=_now_iso(),
        message="开始用 BaiduPCS-Go 转存并下载百度云资源",
    )
    try:
        _append_resource_import_log(task_id, f"百度分享链接：{payload.baidu_url}")
        result = download_first_episodes_from_baidupcs_share(
            payload.baidu_url,
            payload.extract_code,
            destination_dir,
            limit=payload.episode_limit,
            recursive=payload.recursive,
            max_depth=payload.max_depth,
            drama_name=payload.drama_name,
            remote_name=payload.drama_name or f"project_{payload.project_id}",
        )
        downloaded_paths = [item["local_path"] for item in result.get("downloaded") or []]
        _update_resource_import_task(
            task_id,
            progress=45,
            message=f"下载完成：{len(downloaded_paths)} 个视频，开始扫描入库",
            downloaded=result.get("downloaded") or [],
            selected=result.get("selected") or [],
        )
        _append_resource_import_log(task_id, f"下载完成：{len(downloaded_paths)} 个视频")

        scan = scan_videos(project_id=payload.project_id)
        video_ids = _video_ids_for_paths(payload.project_id, downloaded_paths)
        _update_resource_import_task(
            task_id,
            progress=65,
            message=f"扫描完成：入库 {scan.indexed} 个，匹配 {len(video_ids)} 个下载素材",
            scan=scan.model_dump(),
            video_ids=video_ids,
        )
        if scan.failed:
            _append_resource_import_log(task_id, f"扫描失败 {len(scan.failed)} 个：{'；'.join(scan.failed)}", level="warning")
        if not video_ids:
            raise RuntimeError("下载完成，但没有匹配到可进入剪辑管道的视频记录")

        pipeline_result = create_pipeline_runs(
            payload.project_id,
            PipelineRunCreate(
                template_key=payload.pipeline_template_key,
                source_video_ids=video_ids,
                params={},
            ),
            enqueue=payload.enqueue_pipeline,
        )
        pipeline_runs = pipeline_result.get("runs") or []
        _update_resource_import_task(
            task_id,
            status="succeeded",
            progress=100,
            message=f"导入完成：{len(video_ids)} 个素材，创建 {len(pipeline_runs)} 个剪辑任务",
            pipeline_runs=pipeline_runs,
            finished_at=_now_iso(),
        )
        _append_resource_import_log(task_id, f"剪辑任务已创建：{len(pipeline_runs)} 个")
    except BaiduPCSError as exc:
        _fail_resource_import_task(task_id, f"BaiduPCS-Go 下载失败：{exc}")
    except Exception as exc:  # noqa: BLE001 - task status must preserve operational errors.
        _fail_resource_import_task(task_id, str(exc))


def _video_ids_for_paths(project_id: int, paths: list[str]) -> list[int]:
    if not paths:
        return []
    normalized = [str(Path(path)) for path in paths]
    placeholders = ",".join("?" for _ in normalized)
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT id, path
            FROM videos
            WHERE project_id = ? AND path IN ({placeholders})
            """,
            [project_id, *normalized],
        ).fetchall()
    id_by_path = {row["path"]: int(row["id"]) for row in rows}
    return [id_by_path[path] for path in normalized if path in id_by_path]


def _fail_resource_import_task(task_id: str, error: str) -> None:
    _append_resource_import_log(task_id, error, level="error")
    _update_resource_import_task(
        task_id,
        status="failed",
        progress=100,
        message=error,
        error=error,
        finished_at=_now_iso(),
    )


def _get_resource_import_task(task_id: str) -> dict:
    with RESOURCE_IMPORT_TASK_LOCK:
        task = RESOURCE_IMPORT_TASKS.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="resource import task not found")
        return {
            **task,
            "downloaded": list(task.get("downloaded") or []),
            "selected": list(task.get("selected") or []),
            "video_ids": list(task.get("video_ids") or []),
            "pipeline_runs": list(task.get("pipeline_runs") or []),
            "logs": list(task.get("logs") or []),
        }


def _update_resource_import_task(task_id: str, **updates) -> None:
    with RESOURCE_IMPORT_TASK_LOCK:
        task = RESOURCE_IMPORT_TASKS.get(task_id)
        if not task:
            return
        task.update(updates)


def _append_resource_import_log(task_id: str, message: str, level: str = "info") -> None:
    with RESOURCE_IMPORT_TASK_LOCK:
        task = RESOURCE_IMPORT_TASKS.get(task_id)
        if not task:
            return
        task.setdefault("logs", []).append({"time": _now_iso(), "level": level, "message": message})


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _get_workflow_task(task_id: str) -> dict:
    with WORKFLOW_TASK_LOCK:
        task = WORKFLOW_TASKS.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="workflow task not found")
        return {
            **task,
            "generated": list(task.get("generated") or []),
            "failed": list(task.get("failed") or []),
            "logs": list(task.get("logs") or []),
        }


def _update_workflow_task(task_id: str, **updates) -> None:
    with WORKFLOW_TASK_LOCK:
        task = WORKFLOW_TASKS.get(task_id)
        if not task:
            return
        task.update(updates)


def _append_workflow_task_log(task_id: str, message: str, level: str = "info") -> None:
    with WORKFLOW_TASK_LOCK:
        task = WORKFLOW_TASKS.get(task_id)
        if not task:
            return
        logs = task.setdefault("logs", [])
        logs.append(
            {
                "time": _now_iso(),
                "level": level,
                "message": message,
            }
        )


def _record_promo_assets(project_id: int, result: dict) -> list[dict]:
    if result.get("status") != "exported":
        return []
    assets = []
    variants = result.get("variants") or []
    if not variants and result.get("output_path"):
        variants = [
            {
                "key": "latest",
                "label": result.get("title") or "推广视频",
                "output_path": result["output_path"],
                "download_url": result.get("download_url") or "/api/promos/latest/download",
                "duration_estimate_seconds": None,
            }
        ]
    for variant in variants:
        output_path = variant.get("output_path")
        if not output_path:
            continue
        asset = record_generated_asset(
            project_id=project_id,
            asset_type="promo",
            title=variant.get("label") or variant.get("title") or result.get("title") or "推广视频",
            description=(result.get("edit_review") or {}).get("storyline") or "",
            output_path=Path(output_path),
            download_url=variant.get("download_url") or result.get("download_url") or "/api/promos/latest/download",
            duration=variant.get("duration_estimate_seconds"),
            metadata={
                "variant": variant,
                "analysis_budget": result.get("analysis_budget"),
                "edit_review": result.get("edit_review"),
                "model_review": result.get("model_review"),
            },
        )
        assets.append(asset)
    return assets


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    index = 1
    while True:
        candidate = path.with_name(f"{path.stem}_{index}{path.suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def _ndjson_response(events: Iterator[dict]) -> StreamingResponse:
    def lines() -> Iterator[str]:
        try:
            for event in events:
                yield json.dumps(event, ensure_ascii=False, default=str) + "\n"
        except Exception as exc:  # noqa: BLE001 - stream structured errors to the active client.
            yield json.dumps({"type": "error", "message": str(exc)}, ensure_ascii=False) + "\n"

    return StreamingResponse(
        lines(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _message(role: str, title: str, body: str, percent: Optional[int] = None, meta: Optional[str] = None) -> dict:
    event: dict = {
        "type": "message",
        "role": role,
        "title": title,
        "body": body,
    }
    if percent is not None:
        event["percent"] = max(0, min(100, percent))
    if meta:
        event["meta"] = meta
    return event


def _iter_highlight_events(engine: str, limit: int, project_id: Optional[int] = None) -> Iterator[dict]:
    engine = "ai"
    resolved_project_id = resolve_project_id(project_id)
    with connect() as conn:
        videos = rows_to_dicts(
            conn.execute("SELECT * FROM videos WHERE project_id = ? ORDER BY id", (resolved_project_id,)).fetchall()
        )
    if limit > 0:
        videos = videos[:limit]

    generated = []
    total = len(videos)
    yield _message(
        "system",
        "高光生成启动",
        f"已加载 {total} 个视频，开始按本地峰值、台词分析、画面复评和复核流程生成候选片段。",
        percent=8,
    )

    if not videos:
        yield _message("result", "没有可处理视频", "请先上传并扫描视频后再生成高光。", percent=100)
        yield {"type": "trace", "trace": {"kind": "highlights", "data": generated}}
        yield {"type": "done", "result": {"generated": generated}, "percent": 100}
        return

    for video_index, video in enumerate(videos):
        source = Path(video["path"])
        duration = float(video.get("duration") or 0)
        video_percent = 12 + int(video_index / max(total, 1) * 70)
        yield _message(
            "system",
            "分析视频",
            f"{video['name']}：读取音频峰值并生成初始候选窗口。",
            percent=video_percent,
            meta=f"{video_index + 1}/{total}",
        )
        suggestions = suggest_audio_peak_clips(source, duration)
        yield _message(
            "model",
            "本地候选完成",
            f"{video['name']}：识别到 {len(suggestions)} 个候选片段，开始进入模型转写、台词分析和画面复评。",
            percent=min(video_percent + 4, 88),
        )
        suggestions, model_review = enrich_suggestions_with_ai(video, suggestions)
        yield _message(
            "model",
            "模型复评完成",
            f"{video['name']}：模型复评完成，开始导出候选片段。",
            percent=min(video_percent + 12, 90),
        )

        for suggestion_index, suggestion in enumerate(suggestions):
            output = get_settings().output_dir / (
                f"{source.stem.replace(' ', '_')}_auto_{format_time(suggestion['start'])}_{format_time(suggestion['end'])}.mp4"
            )
            clip_meta = f"{_format_seconds(suggestion['start'])}s - {_format_seconds(suggestion['end'])}s"
            try:
                cut_clip(source, output, suggestion["start"], suggestion["end"])
            except Exception as exc:  # noqa: BLE001 - continue batch and report failures.
                failed_item = {
                    "video_id": video["id"],
                    "video_name": video["name"],
                    "status": "failed",
                    "error": str(exc),
                    "engine": engine,
                }
                generated.append(failed_item)
                yield _message(
                    "result",
                    "片段导出失败",
                    f"{video['name']}：{exc}",
                    percent=min(video_percent + 18 + suggestion_index, 94),
                    meta=clip_meta,
                )
                continue
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
                        f"{suggestion['reason']} | engine={engine}",
                        str(output),
                    ),
                )
                clip_id = cursor.lastrowid
            asset = record_generated_asset(
                project_id=resolved_project_id,
                source_video_id=video["id"],
                clip_id=clip_id,
                asset_type="highlight",
                title=f"{video['name']} 高光片段",
                description=suggestion.get("reason", ""),
                output_path=output,
                download_url=f"/api/clips/{clip_id}/download",
                duration=suggestion["end"] - suggestion["start"],
                metadata={"engine": engine, "suggestion": suggestion, "model_review": model_review},
            )
            generated_item = {
                "asset_id": asset["id"],
                "clip_id": clip_id,
                "video_id": video["id"],
                "video_name": video["name"],
                "status": "exported",
                "start": suggestion["start"],
                "end": suggestion["end"],
                "score": suggestion["score"],
                "engine": engine,
                "model_review": model_review,
                "ai": suggestion.get("ai"),
            }
            generated.append(generated_item)
            yield from _highlight_result_messages(
                video_name=video["name"],
                suggestion=suggestion,
                percent=min(video_percent + 18 + suggestion_index, 94),
                meta=clip_meta,
            )

    exported = len([item for item in generated if item.get("status") == "exported"])
    failed = len([item for item in generated if item.get("status") == "failed"])
    yield _message("result", "高光生成完成", f"已导出 {exported} 个高光片段，失败 {failed} 个。", percent=98)
    yield {"type": "trace", "trace": {"kind": "highlights", "data": generated}}
    yield {"type": "done", "result": {"generated": generated}, "percent": 100}


def _highlight_result_messages(video_name: str, suggestion: dict, percent: int, meta: str) -> Iterator[dict]:
    ai = suggestion.get("ai") or {}
    transcript = ai.get("transcript") or {}
    text_review = ai.get("text_review") or {}
    visual_review = ai.get("visual_review") or {}
    yield _message(
        "result",
        "片段已导出",
        f"{video_name}：{suggestion.get('reason') or '候选片段已导出。'}",
        percent=percent,
        meta=meta,
    )
    if transcript.get("text") or transcript.get("error"):
        yield _message("model", "Gemini 转写", transcript.get("text") or transcript.get("error"), percent=percent, meta=meta)
    text_lines = [
        text_review.get("summary") or text_review.get("error"),
        f"Hook: {text_review.get('hook')}" if text_review.get("hook") else None,
        f"连贯性: {text_review.get('continuity')}" if text_review.get("continuity") else None,
    ]
    text_body = "\n".join([line for line in text_lines if line])
    if text_body:
        yield _message("model", "GPT 台词分析", text_body, percent=percent, meta=meta)
    visual_lines = [
        visual_review.get("summary") or visual_review.get("error"),
        f"连贯性风险: {visual_review.get('continuity_risk')}" if visual_review.get("continuity_risk") else None,
    ]
    visual_body = "\n".join([line for line in visual_lines if line])
    if visual_body:
        yield _message("model", "Gemini 画面复评", visual_body, percent=percent, meta=meta)


def _iter_promo_events(limit: int, windows_per_video: int, project_id: Optional[int] = None) -> Iterator[dict]:
    resolved_project_id = resolve_project_id(project_id)
    with connect() as conn:
        videos = rows_to_dicts(
            conn.execute("SELECT * FROM videos WHERE project_id = ? ORDER BY id", (resolved_project_id,)).fetchall()
        )
    if not videos:
        yield {"type": "error", "message": "no uploaded videos"}
        return

    safe_limit = max(1, min(20, limit))
    safe_windows = max(1, min(4, windows_per_video))
    yield _message(
        "system",
        "推广视频生成启动",
        f"将分析 {safe_limit} 个视频，每个视频提取 {safe_windows} 个候选窗口。",
        percent=10,
    )
    yield _message("model", "候选分析开始", "开始抽取候选片段，并进入 GPT 草案、Gemini 审核、GPT 最终决策流程。", percent=18)
    result = generate_promo_video(videos, limit=safe_limit, windows_per_video=safe_windows)
    assets = _record_promo_assets(resolved_project_id, result)
    if assets:
        result["asset_ids"] = [asset["id"] for asset in assets]
    yield from _promo_result_messages(result)
    yield {"type": "trace", "trace": {"kind": "promo", "data": result}}
    yield {"type": "done", "result": result, "percent": 100}


def _promo_result_messages(result: dict) -> Iterator[dict]:
    edit_review = result.get("edit_review") or {}
    yield _message(
        "model",
        "双模型审片完成",
        "\n".join(
            [
                line
                for line in [
                    f"故事线: {edit_review.get('storyline')}" if edit_review.get("storyline") else None,
                    f"状态: {result.get('status')}" if result.get("status") else None,
                    f"错误: {result.get('error')}" if result.get("error") else None,
                ]
                if line
            ]
        )
        or "审片流程已完成。",
        percent=72,
    )

    draft = edit_review.get("gpt_draft") or {}
    if draft.get("storyline") or draft.get("continuity_notes") or draft.get("error"):
        yield _message(
            "model",
            "GPT 草案",
            "\n".join(
                [
                    line
                    for line in [
                        draft.get("storyline") or draft.get("error"),
                        f"连续性: {draft.get('continuity_notes')}" if draft.get("continuity_notes") else None,
                    ]
                    if line
                ]
            ),
            percent=78,
        )

    gemini_review = edit_review.get("gemini_review") or {}
    if gemini_review.get("reason") or gemini_review.get("continuity_risks") or gemini_review.get("error"):
        risks = gemini_review.get("continuity_risks")
        yield _message(
            "model",
            "Gemini 审核",
            "\n".join(
                [
                    line
                    for line in [
                        gemini_review.get("reason") or gemini_review.get("error"),
                        f"风险: {'；'.join(risks)}" if risks else None,
                    ]
                    if line
                ]
            ),
            percent=84,
        )

    final = edit_review.get("gpt_final") or {}
    if final.get("decision_reason") or final.get("continuity_notes") or final.get("error"):
        yield _message(
            "model",
            "GPT 最终决定",
            "\n".join(
                [
                    line
                    for line in [
                        final.get("decision_reason") or final.get("error"),
                        f"连续性: {final.get('continuity_notes')}" if final.get("continuity_notes") else None,
                    ]
                    if line
                ]
            ),
            percent=88,
        )

    variants = result.get("variants") or []
    yield _message(
        "result",
        "推广视频生成完成" if result.get("status") == "exported" else "推广视频生成失败",
        f"已生成 {len(variants) or 1} 个版本。" if result.get("status") == "exported" else result.get("error", "没有可用推广片段。"),
        percent=96,
    )


def _format_seconds(value: object) -> str:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "0.00"
