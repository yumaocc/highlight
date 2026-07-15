# Pipeline Implementation Log

## 2026-06-29: Phase 0/1 Backend API Slice

### Implemented

- Stabilized generated asset recording for pipeline runs.
  - `record_generated_asset` now accepts `pipeline_run_id`.
  - `record_generated_asset` now accepts `pipeline_step_id`.
  - New generated assets can be traced back to the pipeline run and step that
    produced them.
- Added `prompt_snapshot_json` to `pipeline_runs`.
  - New databases include the column in the base schema.
  - Existing databases get the column through migration.
- Expanded `PipelineRunCreate`.
  - Supports `source_video_ids` for batch creation.
  - Keeps `source_video_id` for compatibility with the existing single-video
    backend helper.
  - Supports optional `prompt_config_ids`.
- Exposed official pipeline APIs from `highlight-service`.
  - `GET /api/pipeline-templates`
  - `GET /api/pipeline-templates/{template_key}`
  - `POST /api/projects/{project_id}/pipeline-runs`
  - `GET /api/projects/{project_id}/pipeline-runs`
  - `GET /api/pipeline-runs/{run_id}`
  - `GET /api/pipeline-runs/{run_id}/steps`
  - `GET /api/pipeline-runs/{run_id}/artifacts`
  - `GET /api/pipeline-runs/{run_id}/generated-assets`
  - `POST /api/pipeline-runs/{run_id}/cancel`
- Added pipeline query helpers.
  - List templates.
  - Get one template.
  - List runs by project.
  - Get run detail with steps.
  - List run artifacts.
  - List generated assets by run.
  - Cancel pending runs.
- Added prompt snapshot capture at run creation time.
  - If `prompt_config_ids` are provided, those prompts are snapshotted.
  - Otherwise enabled `video_generation` prompts are snapshotted.
- Made single-video template batch behavior explicit.
  - A request with multiple `source_video_ids` creates one run per source
    video.
  - Each run executes independently and returns its own final state.
- Added frontend pipeline types.
  - `PipelineTemplate`
  - `PipelineRun`
  - `PipelineStep`
  - `PipelineArtifact`
  - `PipelineRunCreatePayload`
- Added frontend pipeline service functions in the existing API client.

### Files Changed

- `apps/highlight-service/app/db.py`
- `apps/highlight-service/app/projects.py`
- `apps/highlight-service/app/models.py`
- `apps/highlight-service/app/pipeline.py`
- `apps/highlight-service/app/main.py`
- `apps/highlight-cutter/frontend/src/types/dashboard.ts`
- `apps/highlight-cutter/frontend/src/services/api.ts`

### Current Limitations

- Pipeline execution is still synchronous.
- Frontend UI does not yet use the new pipeline APIs.
- `promo_single` still depends on current `generate_promo_video` behavior and
  should be verified with real source videos before making it the primary UI
  path.
- Cancel only works for pending runs. Running synchronous runs cannot be
  interrupted yet.

### Verification

- Passed:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-service
env PYTHONPYCACHEPREFIX=/private/tmp/highlight-pycache python3 -m py_compile app/*.py
```

- Passed:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-service
.venv/bin/python -c "from app.main import app; print(len(app.routes))"
```

- Passed:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-cutter/frontend
pnpm build
```

## 2026-06-30: Use Story Context And Reference Frames For GPT Image 2 Intro/Outro

### Implemented

- Improved final-video intro/outro generation quality.
- The intro/outro image prompt now includes selected source video names, model
  review summary, quality notes, keep/drop decision context, retained story
  segment reasons, and viewer-facing promo copy.
- The pipeline extracts a representative frame from kept story segments and
  passes it to GPT Image 2 as `reference_image_path`.
- GPT Image 2 is now instructed to base the image on the reference frame's
  characters, clothes, scene mood, and short-drama texture instead of making a
  generic poster.
- FFmpeg still converts the generated image into intro/outro video segments and
  concatenates them with the final render.
- Restarted `highlight-service` so the running backend loads the new reference
  frame logic.

### Files Changed

- `apps/highlight-service/app/pipeline.py`
- `apps/highlight-service/app/ai_clients.py`
- `docs/PIPELINE_IMPLEMENTATION_LOG.md`

### Verification

- Passed:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-service
env PYTHONPYCACHEPREFIX=/private/tmp/highlight-pycache python3 -m py_compile app/*.py
```

- Passed with project virtualenv:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-service
.venv/bin/python - <<'PY'
from app.pipeline import _review_pack_story_context, _review_pack_reference_frame
from app.ai_clients import build_short_drama_template_visual_prompt
print('helpers-ok')
print('参考图' in build_short_drama_template_visual_prompt('intro','测试','短剧','剧情冲突',1))
PY
```

- Passed against restarted backend:

```bash
curl -s 'http://127.0.0.1:8765/api/health'
curl -s 'http://127.0.0.1:8765/api/pipeline-templates'
```

## 2026-06-30: Equalize Short-Drama Workflow Card Sizes

### Implemented

- Updated the short-drama workbench layout so the four main workflow cards use
  equal column widths on desktop.
- Added fixed, consistent card heights for desktop/tablet while allowing mobile
  cards to become natural-height single-column sections.
- Constrained overflowing content inside cards with internal scrolling instead
  of allowing each card to grow to a different height.
- Adjusted upload, source-list, preview, and publish sections to sit inside the
  same card shell dimensions.

### Files Changed

- `apps/highlight-cutter/frontend/src/pages/index.tsx`
- `apps/highlight-cutter/frontend/src/global.css`
- `docs/PIPELINE_IMPLEMENTATION_LOG.md`

### Verification

- Passed:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-cutter/frontend
pnpm build
```

Browser visual verification was skipped because Chrome DevTools MCP was blocked
by an existing browser profile lock.

## 2026-06-30: Add Short-Drama Project List And Delete Action

### Implemented

- Added a project list drawer on the short-drama clipping page.
- The list shows existing projects, status, material count, generated asset
  count, and update time.
- Added quick project switching from the list.
- Added guarded project deletion from the list.
- Project deletion now removes:
  - project row,
  - source video rows,
  - generated asset rows,
  - clip rows,
  - pipeline runs, sources, steps, jobs, and artifacts,
  - the project's uploaded source folder,
  - run-scoped work folders for proxy/clip/cover/outro/review-pack files.
- Exported output videos are preserved under the service output directory.
- Deletion is rejected when a project still has pending or running pipeline
  tasks.

### Files Changed

- `apps/highlight-service/app/projects.py`
- `apps/highlight-cutter/frontend/src/services/api.ts`
- `apps/highlight-cutter/frontend/src/pages/index.tsx`
- `docs/PIPELINE_IMPLEMENTATION_LOG.md`
- `docs/PIPELINE_TASK_TRACKER.md`

### Verification

- Passed:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-service
env PYTHONPYCACHEPREFIX=/private/tmp/highlight-pycache python3 -m py_compile app/*.py
```

- Passed:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-cutter/frontend
pnpm build
```

- Passed against the running backend:

```bash
curl -s 'http://127.0.0.1:8765/api/projects'
```

Browser visual verification was skipped because Chrome DevTools MCP was blocked
by an existing browser profile lock.

## 2026-06-30: Make Intro/Outro Explicit Pipeline Steps And Audience-Facing Copy

### Implemented

- Added explicit pipeline processors:
  - `generate_review_cover` / `生成首秒封面`
  - `generate_outro_cta` / `生成片尾引导`
- Added these steps to final-video pipelines:
  - `promo_single`
  - `promo_variants`
  - `story_promo_mix`
  - `story_quality_cut`
- Final rendering now reuses the generated intro/outro step outputs and
  concatenates them before and after the main video body.
- Intro and outro are mandatory for final output videos. If GPT image generation
  fails, the service falls back to rendered text cards so the final video still
  has a beginning and ending segment.
- Pipeline run detail now shows intro/outro step summaries.
- Rewrote promotional copy to speak to viewers instead of operators. Copy no
  longer says things like "已生成", "这版只留", or explains the editing process.

### Files Changed

- `apps/highlight-service/app/pipeline.py`
- `apps/highlight-service/app/projects.py`
- `apps/highlight-cutter/frontend/src/components/dashboard/PipelineFlowCard.tsx`
- `docs/PIPELINE_IMPLEMENTATION_LOG.md`
- `docs/PIPELINE_TASK_TRACKER.md`

### Verification

- Passed:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-service
env PYTHONPYCACHEPREFIX=/private/tmp/highlight-pycache python3 -m py_compile app/*.py
```

- Passed:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-cutter/frontend
pnpm build
```

- Passed with project virtualenv:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-service
.venv/bin/python - <<'PY'
from app.pipeline import get_pipeline_template
for key in ['promo_single','promo_variants','story_promo_mix','story_quality_cut']:
    print(key, ' -> '.join(get_pipeline_template(key)['steps']))
PY
```

The system `python3` import check is not usable for this module because that
environment does not have `pydantic_settings`; the project `.venv` does.

## 2026-06-30: Simplify Short-Drama Workbench Flow

### Implemented

- Replaced the main short-drama page tab workflow with a linear production flow:
  1. Upload materials.
  2. Generate video.
  3. Preview video.
  4. Publish.
- The generation step defaults to the current selected project's uploaded
  videos and exposes a single primary `生成视频` action.
- Kept advanced run details available from the recent generation list instead
  of making users navigate a separate tab first.
- Fixed the `name 'run' is not defined` pipeline executor bug by using the
  template key from the `template` argument inside `_execute_run`.
- Restarted `highlight-service` so the running backend loads the
  `generate_review_cover` and `generate_outro_cta` processors.

### Files Changed

- `apps/highlight-service/app/pipeline.py`
- `apps/highlight-cutter/frontend/src/pages/index.tsx`
- `docs/PIPELINE_IMPLEMENTATION_LOG.md`

### Verification

- Passed:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-service
env PYTHONPYCACHEPREFIX=/private/tmp/highlight-pycache python3 -m py_compile app/*.py
```

- Passed:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-cutter/frontend
pnpm build
```

- Passed against the restarted backend:

```bash
curl -s 'http://127.0.0.1:8765/api/pipeline-templates'
```

The response includes `generate_review_cover` and `generate_outro_cta` in the
final-video templates. Existing failed runs remain failed and need to be
recreated.

- Note: running `python3 -m py_compile app/*.py` without
  `PYTHONPYCACHEPREFIX` failed in the sandbox because Python attempted to write
  `.pyc` files under `/Users/q/Library/Caches/com.apple.python`.
- Note: importing `app.main` with system `python3` failed because the system
  interpreter does not have backend dependencies such as `pydantic_settings`.
  The project `.venv/bin/python` import check passed.

### Next Step

Implement the frontend project pipeline workflow:

- load templates,
- select source videos,
- create pipeline runs,
- list run history,
- inspect steps/artifacts/generated assets.

## 2026-06-29: Frontend Pipeline Workflow Entry

### Implemented

- Added a task tracker for completed and pending pipeline work.
  - See `docs/PIPELINE_TASK_TRACKER.md`.
- Added a project-level pipeline generation panel to the console.
  - Loads pipeline templates from `GET /api/pipeline-templates`.
  - Lets the user select one or more source videos.
  - Lets the user choose a template and configure numeric template params.
  - Starts pipeline runs through `POST /api/projects/{project_id}/pipeline-runs`.
  - Refreshes generated assets and project counters after completion.
- Added pipeline run history to the main page.
  - Shows template, source video, status, progress, and current step.
  - Provides a detail drawer for each run.
- Added run detail inspection.
  - Loads run detail from `GET /api/pipeline-runs/{run_id}`.
  - Loads artifacts from `GET /api/pipeline-runs/{run_id}/artifacts`.
  - Displays step timeline and artifact table.
- Kept old generation controls in place for now.
  - This preserves the current working flow while the new pipeline workflow is
    validated with real videos.

### Files Changed

- `apps/highlight-cutter/frontend/src/components/dashboard/PipelineFlowCard.tsx`
- `apps/highlight-cutter/frontend/src/pages/index.tsx`

### Verification

- Passed:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-service
env PYTHONPYCACHEPREFIX=/private/tmp/highlight-pycache python3 -m py_compile app/*.py
```

- Passed:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-cutter/frontend
pnpm build
```

- Passed on a temporary fresh backend instance at port `8766`:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-service
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8766
curl -s http://127.0.0.1:8766/api/pipeline-templates
curl -s http://127.0.0.1:8766/api/projects/1/pipeline-runs
curl -s http://127.0.0.1:8766/api/health
```

- Note: the already-running service on `8765` returned 404 for
  `/api/pipeline-templates` because it was started before these route changes.
  Restart `highlight-service` before testing the new pipeline UI against port
  `8765`.

### Next Step

Validate the pipeline workflow in a running browser with a real or sample
source video, then decide whether to replace the old generation buttons with
pipeline-template actions.

## 2026-06-29: Promo Variants And Legacy Button Migration

### Implemented

- Added first-class `promo_variants` pipeline template.
  - Input scope: `single_video`.
  - Output cardinality: `many`.
  - Steps: `probe_video -> plan_promo_variants -> render_promo_variants`.
- Added promo variant mode support to `generate_promo_video`.
  - Default behavior remains `variant_mode="single"` for compatibility.
  - Pipeline `promo_variants` calls `variant_mode="all"`.
  - The old promo endpoints keep their previous single-final-version behavior
    unless explicitly changed later.
- Added pipeline processors:
  - `plan_promo_variants`
  - `render_promo_variants`
- Migrated old frontend generation buttons to pipeline creation.
  - High-light button now creates `highlight_clip` runs.
  - Promo button now creates `promo_single` runs.
  - Source video resolution order:
    1. selected videos in the pipeline panel,
    2. currently selected source video,
    3. all project videos.

### Files Changed

- `apps/highlight-service/app/promo_pipeline.py`
- `apps/highlight-service/app/pipeline.py`
- `apps/highlight-cutter/frontend/src/pages/index.tsx`
- `docs/PIPELINE_TASK_TRACKER.md`

### Verification

- Passed:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-service
env PYTHONPYCACHEPREFIX=/private/tmp/highlight-pycache python3 -m py_compile app/*.py
```

- Passed:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-cutter/frontend
pnpm build
```

- Passed on a temporary fresh backend instance at port `8766`:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-service
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8766
curl -s http://127.0.0.1:8766/api/pipeline-templates
```

The templates response included `highlight_clip`, `promo_single`, and
`promo_variants`.
- Passed after restarting the normal backend on `8765`:

```bash
curl -s http://127.0.0.1:8765/api/pipeline-templates
curl -s http://127.0.0.1:8001/api/pipeline-templates
```

## 2026-06-29: Frontend Folder Upload

### Implemented

- Added folder selection for source material upload in the materials tab.
  - Keeps the existing drag-and-drop and multi-file picker behavior.
  - Adds an Ant Design `Upload` directory picker button.
  - Filters selected folder contents to supported video extensions before
    calling the existing batch upload API.
- Made the source material list open automatically when videos exist.
  - This prevents successful folder uploads from looking empty because the
    list panel stayed collapsed.
- Updated upload copy to explain that both files and folders are supported.
- Kept the backend upload contract unchanged.
  - `/api/upload` already accepts a `files` batch.

### Files Changed

- `apps/highlight-cutter/frontend/src/components/dashboard/WorkbenchHero.tsx`
- `apps/highlight-cutter/frontend/src/components/dashboard/VideoTableCard.tsx`
- `apps/highlight-cutter/frontend/src/global.css`
- `apps/highlight-cutter/frontend/src/pages/index.tsx`
- `docs/PIPELINE_IMPLEMENTATION_LOG.md`
- `docs/PIPELINE_TASK_TRACKER.md`

### Verification

- Passed:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-cutter/frontend
pnpm build
```

- Passed browser check:
  - `http://127.0.0.1:8001/` shows project `秘书大人不好惹` with `62 个素材`.
  - Materials tab source list is expanded and displays the uploaded videos.

## 2026-06-29: Pipeline Source Batch Selection

### Implemented

- Added batch controls to the pipeline source selector.
  - Shows selected source count versus total source count.
  - Adds `全选` to select all uploaded source videos in the current project.
  - Adds `清空` to clear the current source selection.
- Cleans stale selected ids when the current project's video list changes.
- Keeps the backend pipeline API unchanged.

### Files Changed

- `apps/highlight-cutter/frontend/src/components/dashboard/PipelineFlowCard.tsx`
- `apps/highlight-cutter/frontend/src/global.css`
- `docs/PIPELINE_IMPLEMENTATION_LOG.md`
- `docs/PIPELINE_TASK_TRACKER.md`

### Verification

- Passed:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-cutter/frontend
pnpm build
```

- Passed browser check:
  - In `生成流程`, the source selector shows `已选 0 / 62 个素材`.
  - Clicking `全选` changes it to `已选 62 / 62 个素材`.
  - `启动管道` becomes enabled after selecting all sources.

## 2026-06-29: Project Data Isolation Tightening

### Implemented

- Audited project-scoped data access.
  - Project video lists are filtered by `project_id`.
  - Project generated assets are filtered by `project_id`.
  - Project pipeline runs are filtered by `project_id`.
  - Pipeline run creation validates that every selected source video belongs to
    the target project.
- Tightened detail endpoints with optional project validation.
  - `GET /api/videos/{video_id}?project_id=...`
  - `GET /api/pipeline-runs/{run_id}?project_id=...`
  - `GET /api/pipeline-runs/{run_id}/steps?project_id=...`
  - `GET /api/pipeline-runs/{run_id}/artifacts?project_id=...`
  - `GET /api/pipeline-runs/{run_id}/generated-assets?project_id=...`
  - `POST /api/pipeline-runs/{run_id}/cancel?project_id=...`
- Updated frontend detail calls to pass the selected project id.
- Cleared project-scoped frontend state immediately when switching projects so
  old project rows do not remain visible while new requests are loading.

### Files Changed

- `apps/highlight-service/app/main.py`
- `apps/highlight-service/app/pipeline.py`
- `apps/highlight-cutter/frontend/src/services/api.ts`
- `apps/highlight-cutter/frontend/src/pages/index.tsx`
- `docs/PIPELINE_IMPLEMENTATION_LOG.md`
- `docs/PIPELINE_TASK_TRACKER.md`

### Verification

- Passed:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-service
env PYTHONPYCACHEPREFIX=/private/tmp/highlight-pycache python3 -m py_compile app/*.py
```

- Passed:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-cutter/frontend
pnpm build
```

- Passed on temporary backend port `8766`:
  - `GET /api/videos/83?project_id=3` returns `200`.
  - `GET /api/videos/83?project_id=1` returns `404`.
  - `GET /api/pipeline-runs/2?project_id=3` returns `200`.
  - `GET /api/pipeline-runs/2?project_id=1` returns `404`.
  - `GET /api/pipeline-runs/2/steps?project_id=3` returns `200`.
  - `GET /api/pipeline-runs/2/steps?project_id=1` returns `404`.
  - `GET /api/pipeline-runs/2/artifacts?project_id=3` returns `200`.
  - `GET /api/pipeline-runs/2/artifacts?project_id=1` returns `404`.

### Remaining Isolation Gaps

- Download URLs are still global by output asset/variant path.
  - Example: promo download endpoints under `/api/promos/.../download`.
  - Generated assets are listed by project, but the raw download endpoint does
    not yet enforce project ownership.
- Runtime output/work directories are still shared for some generated files.
  - Project-scoped asset records exist, but physical generated filenames can be
    overwritten by later runs if processors emit shared names.

## 2026-06-30: Multi-Source Story Promo Pipeline

### Implemented

- Added generic run strategy metadata to pipeline templates.
  - `per_source`: selected sources create one run per source.
  - `aggregate`: selected sources create one aggregate run.
- Added `pipeline_run_sources`.
  - Stores all source videos attached to a pipeline run.
  - Enables multi-source runs without overloading `pipeline_runs.source_video_id`.
- Added `story_promo_mix` template.
  - Chinese name: `剧情引流总剪`.
  - Input: `multi_video`.
  - Output: `one`.
  - Strategy: `aggregate`.
  - Steps: `probe_source_collection -> plan_story_promo_mix -> render_story_promo_mix`.
- Added aggregate processors for the first MVP.
  - `probe_source_collection` records selected source metadata.
  - `plan_story_promo_mix` stores target duration and candidate window params.
  - `render_story_promo_mix` reuses current promo generation over all selected
    videos and records one generated promo asset.
- Changed aggregate run creation.
  - Multiple selected source videos create exactly one run.
  - All source ids are validated against the selected project.
  - Aggregate templates are always enqueued by the API to avoid blocking HTTP
    requests with long multi-video generation.
- Updated frontend template display.
  - Shows `剧情引流总剪 · 多对一`.
  - Shows selected source count and whether selection creates one aggregate task
    or many per-source tasks.
  - Disables the queue switch for aggregate templates because queue execution is
    mandatory.

### Files Changed

- `apps/highlight-service/app/db.py`
- `apps/highlight-service/app/main.py`
- `apps/highlight-service/app/pipeline.py`
- `apps/highlight-cutter/frontend/src/types/dashboard.ts`
- `apps/highlight-cutter/frontend/src/components/dashboard/PipelineFlowCard.tsx`
- `docs/PIPELINE_IMPLEMENTATION_LOG.md`
- `docs/PIPELINE_TASK_TRACKER.md`

### Verification

- Passed:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-service
env PYTHONPYCACHEPREFIX=/private/tmp/highlight-pycache python3 -m py_compile app/*.py
```

- Passed:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-cutter/frontend
pnpm build
```

- Passed on temporary backend port `8766`:
  - `GET /api/pipeline-templates` includes `story_promo_mix` with
    `run_strategy=aggregate`.
  - Creating `story_promo_mix` with two source videos returned one pending run
    with `source_count=2`.
  - The run returned two `sources` rows.
  - The verification run was removed from the local database after checking.

### Current Limitations

- `render_story_promo_mix` is an MVP bridge over the existing promo generation
  function. It analyzes multiple videos, but the dedicated two-stage
  single-episode-summary then project-level-story-plan flow is still pending.
- Promo output files still use shared promo filenames from the existing renderer.
  Project-scoped output paths should be addressed next.

Both returned the three pipeline templates through the API and frontend proxy.
- Browser visual verification is still pending because Chrome DevTools MCP is
  locked by an existing browser profile instance.

### Next Step

Perform browser E2E validation with a real source video when browser automation
is available. In parallel, start restructuring the main page into project tabs.

## 2026-06-29: Project Workspace Tabs

### Implemented

- Restructured the main workspace into Ant Design tabs.
  - `素材`: upload, quick generation actions, and source video list.
  - `生成流程`: pipeline template selection, source video selection, run history,
    and run detail drawer.
  - `生成结果`: generated project assets.
  - `过程记录`: existing model/trace output panel.
- Kept existing page route and layout to avoid introducing a larger routing
  change during the pipeline migration.

### Files Changed

- `apps/highlight-cutter/frontend/src/pages/index.tsx`
- `docs/PIPELINE_TASK_TRACKER.md`

### Verification

- Passed:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-service
env PYTHONPYCACHEPREFIX=/private/tmp/highlight-pycache python3 -m py_compile app/*.py
```

- Passed:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-cutter/frontend
pnpm build
```

- Passed after restarting the normal backend on `8765`:

```bash
curl -s http://127.0.0.1:8765/api/pipeline-jobs
curl -s -X POST http://127.0.0.1:8765/api/pipeline-jobs/run-next
curl -s http://127.0.0.1:8765/api/pipeline-templates
```

`/api/pipeline-jobs` returned `[]`, `/api/pipeline-jobs/run-next` returned
`{"status":"idle"}`, and templates returned all three pipeline templates.

### Next Step

Add generated asset grouping/filtering by pipeline run, template, and source
video, then expose prompt snapshots in the run detail drawer.

## 2026-06-29: Asset Filtering And Prompt Snapshot Display

### Implemented

- Enhanced generated asset display.
  - Filter by asset type.
  - Filter by source video.
  - Filter by pipeline run.
  - Show pipeline template metadata when present.

## 2026-06-30: Story Quality Cut MVP

### Implemented

- Added `docs/STORY_QUALITY_CUT_WORKSPEC.md`.
  - Defines `剧情精剪` as a quality-preserving short-drama edit mode.
  - Keeps useful story material instead of targeting a fixed runtime.
  - Distinguishes it from `剧情引流总剪`, which optimizes for hooks and promo
    appeal.
- Added `story_quality_cut` pipeline template.
  - Chinese name: `剧情精剪`.
  - Input: `multi_video`.
  - Output: `one`.
  - Strategy: `aggregate`.
  - Steps: `probe_source_collection -> plan_story_quality_cut -> render_story_quality_cut`.
  - Params: `keep_policy` with `strict`, `balanced`, and `loose`.
- Added quality-cut processors.
  - `plan_story_quality_cut` creates timestamped keep decisions for the current
    MVP.
  - `render_story_quality_cut` renders kept windows from original source videos
    and concatenates them into one output file.
  - The generated asset uses `asset_type=quality_cut` and records source ids,
    keep policy, kept segments, and plan metadata.
- Added a run-specific promo file download route.
  - `GET /api/promo-files/{filename}/download`
  - Guards against path traversal and only serves `.mp4` files from the promo
    output directory.
- Updated the frontend pipeline form.
  - Select-type template params render with Ant Design `Select`.
  - `keep_policy` displays user-facing Chinese labels.
- Updated generated asset typing to include `quality_cut`.

### Files Changed

- `docs/STORY_QUALITY_CUT_WORKSPEC.md`
- `docs/PIPELINE_IMPLEMENTATION_LOG.md`
- `docs/PIPELINE_TASK_TRACKER.md`
- `apps/highlight-service/app/pipeline.py`
- `apps/highlight-service/app/main.py`
- `apps/highlight-cutter/frontend/src/components/dashboard/PipelineFlowCard.tsx`
- `apps/highlight-cutter/frontend/src/types/dashboard.ts`

### Verification

- Passed on temporary backend port `8766`:
  - `GET /api/pipeline-templates` includes `story_quality_cut`.
  - Creating `story_quality_cut` with two source videos returned one pending
    aggregate run with three expected steps and two source bindings.
  - The verification run was removed from the local database after checking.

### Current Limitations

- This is a pipeline MVP, not the final proxy-video model-review flow.
  - Current planning uses local candidate windows.
  - The next implementation should create low-resolution proxy videos, let a
    multimodal model review the selected episodes, and persist timestamped
    `keep_required`, `keep_optional`, and `drop` decisions.
- A real render was not executed in this step because it can be expensive on
  multi-video source material. The processor path is wired and will execute via
  the existing queue worker.

## 2026-06-30: Story Quality Cut Proxy Videos

### Implemented

- Added reusable proxy video rendering helper.
  - `render_proxy_video` transcodes source videos to model-friendly MP4 proxies.
  - Defaults: max height `480`, `12fps`, low video bitrate, mono low-bitrate
    audio.
  - Proxy videos preserve the original timeline so timestamps can map back to
    source videos.
- Added `create_proxy_videos` pipeline processor.
  - Writes files under `work/proxy/run_{run_id}`.
  - Stores proxy path, source path, source duration, proxy duration, dimensions,
    fps, codec, and source video id in the step artifact.
- Updated `story_quality_cut` template.
  - First step is now `create_proxy_videos`.
  - New params:
    - `proxy_max_height`, default `480`, bounded to `240..720`.
    - `proxy_fps`, default `12`, bounded to `6..24`.
- Updated `plan_story_quality_cut`.
  - Reads the generated proxy artifact.
  - Copies proxy paths into the quality plan and each keep decision.
  - Still uses local candidate windows for keep/drop decisions until model
    review is added.

### Files Changed

- `apps/highlight-service/app/ffmpeg.py`
- `apps/highlight-service/app/pipeline.py`
- `docs/STORY_QUALITY_CUT_WORKSPEC.md`
- `docs/PIPELINE_IMPLEMENTATION_LOG.md`
- `docs/PIPELINE_TASK_TRACKER.md`

### Operational Note

- The running backend service was not restarted because active tasks were
  already running. These code changes will take effect after the backend/worker
  processes are restarted later.

### Remaining Work

- Run real API and source-video validation after the running backend and worker
  can be restarted.
- Add chunked model review if proxy videos exceed model payload limits.

## 2026-06-30: Story Quality Cut Model Review

### Implemented

- Added Gemini proxy-video review.
  - New AI helper: `gemini_watch_story_quality_proxies`.
  - Sends generated proxy MP4 files as inline video parts to Gemini native
    `generateContent`.
  - Asks for timestamped `keep_required`, `keep_optional`, and `drop`
    decisions per source video.
  - Keeps the product rule: no fixed output duration, preserve useful story
    quality first.
- Added default prompt configuration.
  - New prompt key: `story_quality_cut_review`.
  - Seeded as a system `video_generation` prompt so it can be configured from
    the prompt UI after database initialization.
- Updated `story_quality_cut` pipeline steps.
  - `create_proxy_videos`
  - `model_watch_quality_cut`
  - `validate_quality_edit_decisions`
  - `render_story_quality_cut`
- Added model-review processor.
  - Reads proxy artifacts.
  - Uses the run prompt snapshot when `story_quality_cut_review` is present.
  - Falls back to local candidate windows only when the model call fails.
- Added decision validation processor.
  - Rejects decisions with invalid source ids or invalid timestamps.
  - Bounds timestamps to the source video duration.
  - Rejects sub-second fragments.
  - Merges adjacent same-source, same-decision segments.
  - Produces `kept_segments` for the renderer.
- Updated rendering.
  - `render_story_quality_cut` now consumes validated kept segments instead of
    raw model output.

### Files Changed

- `apps/highlight-service/app/ai_clients.py`
- `apps/highlight-service/app/db.py`
- `apps/highlight-service/app/pipeline.py`
- `docs/STORY_QUALITY_CUT_WORKSPEC.md`
- `docs/PIPELINE_IMPLEMENTATION_LOG.md`
- `docs/PIPELINE_TASK_TRACKER.md`

### Verification

- Passed:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-service
env PYTHONPYCACHEPREFIX=/private/tmp/highlight-pycache python3 -m py_compile app/*.py
```

- Passed import checks:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-service
.venv/bin/python -c "from app.pipeline import get_pipeline_template; print(get_pipeline_template('story_quality_cut')['steps'])"
.venv/bin/python -c "from app.ai_clients import gemini_watch_story_quality_proxies; print(gemini_watch_story_quality_proxies([], 'balanced').get('error'))"
```

### Operational Note

- The running backend service and worker were not restarted because active
  tasks were already running. These changes will take effect after the backend
  and worker are restarted later.

### Remaining Work

- Run a real end-to-end `story_quality_cut` job after restart.
- Validate Gemini inline video limits with actual proxy file sizes.
- Add chunked review if selected episodes exceed model payload limits.
- Add richer artifacts such as transcripts and keyframes for difficult
  continuity decisions.

## 2026-06-30: Story Quality Cut Quality Review UI

### Implemented

- Strengthened quality-cut decision validation.
  - Filters very short keep fragments to reduce jump-cut risk.
  - Bridges short gaps between adjacent kept segments from the same source.
  - Preserves the stronger keep label when merging `keep_required` and
    `keep_optional`.
  - Produces per-source summaries with duration, kept seconds, kept ratio, and
    kept segment count.
  - Produces quality risks when an episode keeps too little, keeps almost all
    content, has no kept segments, or has rejected model decisions.
- Added frontend review visibility for `剧情精剪`.
  - The pipeline detail drawer now shows review mode, keep policy, estimated
    output duration, quality notes, risks, per-source keep ratio, all decisions,
    and rejected rows.
  - Uses existing Ant Design components and existing artifact API data.

### Files Changed

- `apps/highlight-service/app/pipeline.py`
- `apps/highlight-cutter/frontend/src/components/dashboard/PipelineFlowCard.tsx`
- `docs/PIPELINE_IMPLEMENTATION_LOG.md`
- `docs/PIPELINE_TASK_TRACKER.md`

### Verification

- Passed:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-service
env PYTHONPYCACHEPREFIX=/private/tmp/highlight-pycache python3 -m py_compile app/*.py
```

- Passed:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-cutter/frontend
pnpm build
```

### Operational Note

- The running backend service was not restarted. UI/backend changes will apply
  after the current service and worker are restarted later.
  - Show `Run #...` and step linkage when present.
- Added prompt snapshot display to pipeline run detail.
  - Shows prompt key, name, and content summary from `prompt_snapshot`.

### Files Changed

- `apps/highlight-cutter/frontend/src/components/dashboard/AssetOutputPanel.tsx`
- `apps/highlight-cutter/frontend/src/components/dashboard/PipelineFlowCard.tsx`
- `apps/highlight-cutter/frontend/src/types/dashboard.ts`
- `docs/PIPELINE_TASK_TRACKER.md`

### Verification

- Passed:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-service
env PYTHONPYCACHEPREFIX=/private/tmp/highlight-pycache python3 -m py_compile app/*.py
```

- Passed:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-cutter/frontend
pnpm build
```

### Next Step

Start queue/worker design implementation, or complete browser E2E validation
first if an available browser automation session is restored.

## 2026-06-29: Queue Foundation

### Implemented

- Added `pipeline_jobs` table.
  - Tracks `run_id`, status, priority, worker lock, attempts, and errors.
- Added queue helpers in `app/pipeline.py`.
  - `enqueue_pipeline_run`
  - `list_pipeline_jobs`
  - `run_next_pipeline_job`
- Added optional queued run creation.
  - `POST /api/projects/{project_id}/pipeline-runs?enqueue=true`
  - Default behavior remains synchronous for current frontend compatibility.
- Added queue inspection/execution APIs.
  - `GET /api/pipeline-jobs`
  - `POST /api/pipeline-jobs/run-next`

### Files Changed

- `apps/highlight-service/app/db.py`
- `apps/highlight-service/app/pipeline.py`
- `apps/highlight-service/app/main.py`
- `docs/PIPELINE_TASK_TRACKER.md`

### Verification

- Passed:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-service
env PYTHONPYCACHEPREFIX=/private/tmp/highlight-pycache python3 -m py_compile app/*.py
```

- Passed:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-cutter/frontend
pnpm build
```

### Next Step

Add a standalone worker command or service loop and frontend polling before
making queued execution the default behavior.

## 2026-06-29: Worker Command And Queue UI

### Implemented

- Added standalone worker command.
  - `.venv/bin/python -m app.worker`
  - `.venv/bin/python -m app.worker --once`
  - Supports `--interval` and `--worker-id`.
- Improved queue cancellation.
  - Canceling a pending run now also marks its pending job as `canceled`.
- Added frontend queue option.
  - Pipeline panel has an `加入队列后台执行` switch.
  - When enabled, run creation calls
    `POST /api/projects/{project_id}/pipeline-runs?enqueue=true`.
- Added frontend polling.
  - While project runs include `pending` or `running`, the page refreshes runs
    and assets every 3 seconds.

### Files Changed

- `apps/highlight-service/app/pipeline.py`
- `apps/highlight-service/app/worker.py`
- `apps/highlight-cutter/frontend/src/services/api.ts`
- `apps/highlight-cutter/frontend/src/components/dashboard/PipelineFlowCard.tsx`
- `apps/highlight-cutter/frontend/src/pages/index.tsx`
- `docs/PIPELINE_TASK_TRACKER.md`

### Verification

- Passed:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-service
env PYTHONPYCACHEPREFIX=/private/tmp/highlight-pycache python3 -m py_compile app/*.py
```

- Passed:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-cutter/frontend
pnpm build
```

- Passed after restarting backend on `8765`:

```bash
curl -s http://127.0.0.1:8765/api/pipeline-jobs
.venv/bin/python -m app.worker --once
curl -s http://127.0.0.1:8001/api/pipeline-templates
```

The worker returned `{"status": "idle"}` on an empty queue.

### Next Step

Implement publish actions for generated assets and keep real-video E2E
validation as the next runtime check.

## 2026-06-29: Generated Asset Publish Entry

### Implemented

- Added single asset publish entry.
  - Each generated asset row has a `发布` action.
  - The action opens `/publish?projectId=...&assetIds=...`.
- Added selected asset publish entry.
  - Generated assets can be selected with checkboxes.
  - `发布选中` opens publish center with selected asset IDs.
- Added publish page query prefill.
  - Reads `projectId` from URL.
  - Reads comma-separated `assetIds` from URL.
  - Loads project assets and fills `assetIds`, `filePaths`, title, and
    description.

### Files Changed

- `apps/highlight-cutter/frontend/src/components/dashboard/AssetOutputPanel.tsx`
- `apps/highlight-cutter/frontend/src/pages/publish/index.tsx`
- `docs/PIPELINE_TASK_TRACKER.md`

### Verification

- Passed:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-service
env PYTHONPYCACHEPREFIX=/private/tmp/highlight-pycache python3 -m py_compile app/*.py
```

- Passed:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-cutter/frontend
pnpm build
```

### Next Step

Continue with project-level publish selection rules and real publish-service
task linkage when the publish backend contract is stable.

## 2026-06-29: Remove Highlight Max Count Param

### Implemented

- Removed `最多片段数` from the `highlight_clip` pipeline template.
- Removed `limit` handling from pipeline highlight rendering.
- Updated the old high-light generation button path so it creates
  `highlight_clip` runs with no arbitrary max-count param.
- Updated design/planning docs to align with the current product direction:
  - `many -> one`: multiple source videos generate one work.
  - `x -> x`: X source videos generate X corresponding works.

### Files Changed

- `apps/highlight-service/app/pipeline.py`
- `apps/highlight-cutter/frontend/src/pages/index.tsx`
- `docs/PIPELINE_DESIGN.md`
- `docs/PIPELINE_DEVELOPMENT_PLAN.md`
- `docs/PIPELINE_TASK_TRACKER.md`

### Next Step

Define concrete templates for the two product modes:

- multi-source to one work,
- X source videos to X works.

### Verification

- Passed:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-service
env PYTHONPYCACHEPREFIX=/private/tmp/highlight-pycache python3 -m py_compile app/*.py
```

- Passed:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-cutter/frontend
pnpm build
```

- Passed after restarting backend on `8765`:

```bash
curl -s http://127.0.0.1:8765/api/pipeline-templates
```

`highlight_clip.params_schema` is now `{}` and no longer returns `limit` /
`最多片段数`.
- Note: `http://127.0.0.1:8001` was not listening during the final proxy check;
  restart the frontend dev server before browser testing.

## 2026-06-29: Remove Legacy Generation Controls From Materials

### Implemented

- Removed generation controls from the materials tab.
  - No generation type selector.
  - No analysis engine selector.
  - No "generate high-light/promo" button.
  - No task progress strip in the material upload area.
- Simplified `WorkbenchHero` into a pure source material upload component.
- Cleaned obsolete dashboard state and handlers tied to the old generation
  controls.
- Generation now starts only from the `生成流程` pipeline panel.

### Files Changed

- `apps/highlight-cutter/frontend/src/components/dashboard/WorkbenchHero.tsx`
- `apps/highlight-cutter/frontend/src/pages/index.tsx`
- `docs/PIPELINE_TASK_TRACKER.md`

### Verification

- Passed:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-service
env PYTHONPYCACHEPREFIX=/private/tmp/highlight-pycache python3 -m py_compile app/*.py
```

- Passed:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-cutter/frontend
pnpm build
```

### Next Step

Restart the frontend dev server and visually confirm the materials tab only
contains upload and source-listing UI.

## 2026-06-30: Drop Source-Video Built-In Outros In Story Quality Cut

### Implemented

- Updated the built-in `story_quality_cut_review` prompt so `剧情精剪` explicitly
  identifies and drops source-video endings/outros.
- Covered common source outro patterns:
  - `未完待续`
  - `下集更精彩`
  - follow/like/favorite CTA
  - `点击左下角看全集` / `看全集`
  - platform CTA slates
  - duplicate promo cards
  - black/frozen ending screens
  - credits and end titles
- Added a hard rule in the Gemini proxy-video review payload so the model still
  receives the source-outro removal requirement even when prompt config changes.
- Added `source_outro` as an allowed decision role for quality-cut model output.
- Updated the current runtime prompt config through the existing prompt API, so
  the rule is visible and editable in `系统设置 -> 提示词配置` under
  `剧情精剪审片 / story_quality_cut_review`.

### Files Changed

- `apps/highlight-service/app/db.py`
- `apps/highlight-service/app/ai_clients.py`
- `docs/PIPELINE_IMPLEMENTATION_LOG.md`
- `docs/PIPELINE_TASK_TRACKER.md`

### Verification

- Passed:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-service
env PYTHONPYCACHEPREFIX=/private/tmp/highlight-pycache python3 -m py_compile app/*.py
```

- Passed against the running backend:

```bash
curl -s 'http://127.0.0.1:8765/api/prompts?category=video_generation'
```

The response includes the updated `story_quality_cut_review` content.

## 2026-07-01: Fix `generate_review_cover` Queue Failure

### Implemented

- Confirmed the `'generate_review_cover'` failure was caused by an old queue
  worker process still running code that did not register the new processor.
- Restarted the failed run after stopping the stale worker.
- Added stale running-job recovery in `run_next_pipeline_job`, so a dead worker
  lock can be returned to `pending` automatically.
- Added resume behavior for completed steps:
  - Already succeeded steps are skipped.
  - Step outputs are restored into execution context before later steps run.
  - Pre-generated review cover and outro segment paths are restored for final
    rendering.
- Cleared stale step output/error/finish timestamps when rerunning a step.

### Files Changed

- `apps/highlight-service/app/pipeline.py`

### Verification

- Passed:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-service
env PYTHONPYCACHEPREFIX=/private/tmp/highlight-pycache python3 -m py_compile app/*.py
```

- Re-ran `pipeline_run` 22 with the current worker code.
- `generate_review_cover` and `generate_outro_cta` both completed.
- Final generated asset:
  - `/Users/q/Desktop/work/highlight/apps/highlight-service/outputs/promos/story_quality_cut_run_22.mp4`
  - duration: about `579.1s`
  - asset id: `8`

### Notes

- The run completed through fallback text cards because the GPT Image 2 request
  failed with `[Errno 8] nodename nor servname provided, or not known`.
- The generated prompt now uses the project display title
  `我应聘保安，女神你咋当众求婚`, not the source filename `5(1)`.

## 2026-07-01: Stabilize Publish Task Status

### Implemented

- Added publish API regression tests for `/api/publish/video`.
- Added a timeout around the legacy `sau_cli.py upload-video` subprocess so a
  stuck platform uploader no longer leaves the publish task in `running`
  forever.
- Added frontend polling for active publish tasks, so the publish center updates
  pending/running tasks until they reach `succeeded`, `failed`, or `canceled`.
- Improved publish task status rendering with localized labels and failed
  progress state.

### Files Changed

- `apps/social-auto-upload/sau_backend.py`
- `apps/social-auto-upload/tests/test_sau_backend_publish.py`
- `apps/highlight-cutter/frontend/src/pages/publish/index.tsx`

### Verification

- Passed:

```bash
cd /Users/q/Desktop/work/highlight/apps/social-auto-upload
.venv/bin/python -m pytest tests
```

- Passed:

```bash
cd /Users/q/Desktop/work/highlight/apps/social-auto-upload
.venv/bin/python -m py_compile sau_backend.py
```

- Passed:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-cutter/frontend
pnpm build
```

### Notes

- `python3 -m py_compile sau_backend.py` fails on this machine because system
  `python3` is too old for existing `match` syntax. The project `.venv` Python
  passes.
- The currently running publish service on port `5409` must be restarted before
  the timeout fix takes effect.

## 2026-07-01: Use Headed Browser For Publish Tasks

### Implemented

- Changed publish-center triggered uploads from `--headless` to `--headed` for
  non-Bilibili platforms, so the browser window is visible during upload.
- Added a regression assertion that `/api/publish/video` passes `--headed` and
  not `--headless` to `sau_cli.py`.
- Restarted the local publish service on port `5409` so the new mode is active.

### Files Changed

- `apps/social-auto-upload/sau_backend.py`
- `apps/social-auto-upload/tests/test_sau_backend_publish.py`
- `docs/PIPELINE_IMPLEMENTATION_LOG.md`

### Verification

- Passed:

```bash
cd /Users/q/Desktop/work/highlight/apps/social-auto-upload
.venv/bin/python -m pytest tests/test_sau_backend_publish.py
.venv/bin/python -m pytest tests
.venv/bin/python -m py_compile sau_backend.py
```

- Confirmed `http://127.0.0.1:5409/api/platforms` responds after restart.

## 2026-07-02: Extend Review Cover Duration

### Implemented

- Changed generated review-cover intro duration from `1.0s` to `1.5s`.
- Centralized review cover and outro CTA durations in pipeline constants.
- Updated review-cover prompt wording from first-second cover to `1.5` second
  cover.
- Updated pre-generated review-pack metadata fallbacks to use the same duration
  constants.

### Files Changed

- `apps/highlight-service/app/pipeline.py`
- `docs/PIPELINE_IMPLEMENTATION_LOG.md`

### Verification

- Passed:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-service
env PYTHONPYCACHEPREFIX=/private/tmp/highlight-pycache python3 -m py_compile app/*.py
```

## 2026-07-02: Make Kuaishou Promotion Task Optional

### Implemented

- Diagnosed Kuaishou publish failure after successful video upload:
  - Upload completed successfully.
  - Failure happened while opening the author-service Ant Design dropdown for
    `关联变现任务`.
  - The dropdown did not become visible within `10000ms`.
- Changed the publish page default so `关联快手变现任务` is not checked by
  default.
- Changed Kuaishou uploader behavior so promotion-task association failure is
  logged as a warning and does not block the final publish click.
- Added a regression test covering that promotion-task failure does not block
  the publish flow.
- Restarted local publish service on port `5409`.

### Files Changed

- `apps/highlight-cutter/frontend/src/pages/publish/index.tsx`
- `apps/social-auto-upload/uploader/ks_uploader/main.py`
- `apps/social-auto-upload/tests/test_kuaishou_uploader.py`
- `docs/PIPELINE_IMPLEMENTATION_LOG.md`

### Verification

- Passed:

```bash
cd /Users/q/Desktop/work/highlight/apps/social-auto-upload
.venv/bin/python -m py_compile sau_backend.py uploader/ks_uploader/main.py
.venv/bin/python -m pytest tests/test_kuaishou_uploader.py tests/test_sau_backend_publish.py
.venv/bin/python -m pytest tests
```

- Passed:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-cutter/frontend
pnpm build
```

- Confirmed `http://127.0.0.1:5409/api/accounts` responds after restart.

## 2026-06-30: Generate Publish Tags With Promo Copy

### Implemented

- Added generated publish tags to promo copy metadata.
- New generated assets now store `metadata.publish_tags`.
- Existing generated assets get fallback publish tags when listed.
- The default tag is always included: `#快来看短剧`.
- Tags are normalized to `#文字内容` format.
- The generated-results panel displays publish tags below the promotional copy.
- The publish page now auto-fills `话题` from selected generated assets and keeps
  tags in `#文字内容` format when creating publish tasks.

### Files Changed

- `apps/highlight-service/app/pipeline.py`
- `apps/highlight-service/app/projects.py`
- `apps/highlight-cutter/frontend/src/components/dashboard/AssetOutputPanel.tsx`
- `apps/highlight-cutter/frontend/src/pages/publish/index.tsx`

### Verification

- Passed:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-service
env PYTHONPYCACHEPREFIX=/private/tmp/highlight-pycache python3 -m py_compile app/*.py
```

- Passed:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-cutter/frontend
pnpm build
```
