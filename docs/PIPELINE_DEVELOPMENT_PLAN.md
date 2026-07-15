# Pipeline Development Plan

## Current Repository Baseline

This plan is based on the current code under `/Users/q/Desktop/work/highlight`.

### Backend State

`apps/highlight-service` already has several pieces needed for the pipeline
direction:

- `app/projects.py`
  - Project CRUD exists.
  - Project asset listing exists.
  - `generated_assets` records are already used by highlight, promo, and manual
    clip flows.
- `app/prompts.py`
  - Prompt CRUD exists.
  - AI client calls already read prompt text by key through `get_prompt_text`.
- `app/db.py`
  - `projects`, `videos`, `generated_assets`, `pipeline_runs`,
    `pipeline_steps`, `artifacts`, and `prompt_configs` tables exist.
  - There is not yet a `pipeline_templates` table.
  - `pipeline_runs` does not yet store `prompt_snapshot_json`.
- `app/pipeline.py`
  - A first pipeline implementation exists with hardcoded templates:
    `highlight_clip` and `promo_single`.
  - It is not currently exposed through `app/main.py` routes.
  - It only accepts one `source_video_id` per request.
  - It has a likely integration mismatch: `pipeline.py` passes
    `pipeline_run_id` / `pipeline_step_id` to `record_generated_asset`, but
    `projects.py` does not currently accept or insert those arguments.
- `app/main.py`
  - The active UI still calls legacy endpoints:
    `/api/highlights/auto/stream` and `/api/promos/generate/stream`.
  - The promo endpoint currently processes a project video list together,
    while the intended model is one source video entering one run.

### Frontend State

`apps/highlight-cutter/frontend` is already a unified console entrypoint, but
the generation workflow is still old-mode-oriented:

- `src/pages/index.tsx`
  - Project selection exists.
  - Upload, scan, source video list, generated asset list, and old generation
    buttons exist.
  - It still uses `mode = highlight | promo` and calls old streaming endpoints.
  - There is no pipeline run list, step detail, artifact view, or template
    selection UI.
- `src/pages/settings/index.tsx`
  - Prompt configuration UI exists.
- `src/services/api.ts`
  - Project, video, asset, old highlight, and old promo APIs exist.
  - Pipeline APIs do not exist.
- `src/types/dashboard.ts`
  - Project, video, generated asset, trace, and stream types exist.
  - Pipeline template/run/step/artifact types do not exist.
- `.umirc.ts`
  - Routes exist for `/`, `/publish`, `/accounts`, `/accounts/login`, and
    `/settings`.
  - No dedicated project detail route exists yet.

### Product Direction To Preserve

- The short-drama project is the main unit.
- A source video is the default pipeline input.
- Batch generation means creating multiple one-video runs.
- Product generation modes are expressed through templates and should primarily
  fit either `many -> one` or `x -> x`.
- Queue execution is desired, but MVP can run synchronously if run/step state is
  persisted.
- Rollback and artifact reuse are out of scope for the MVP.

## Delivery Strategy

Do this as a migration from the current working flow to the pipeline flow, not
as a rewrite.

The safest path is:

```text
1. Stabilize existing half-landed pipeline code.
2. Expose official pipeline APIs while keeping old endpoints working.
3. Add frontend pipeline views behind the existing project workflow.
4. Move generation buttons to pipeline templates.
5. Add queued execution after the synchronous pipeline contract is stable.
6. Connect generated assets to publish actions.
```

Old endpoints can stay temporarily as compatibility wrappers until the frontend
fully uses pipeline runs.

## Phase 0: Stabilize Current Pipeline Foundation

Goal: make the existing backend pipeline code internally consistent before
building UI on top of it.

### Backend Tasks

- Fix `record_generated_asset` in `apps/highlight-service/app/projects.py`:
  - Accept optional `pipeline_run_id`.
  - Accept optional `pipeline_step_id`.
  - Insert those fields into `generated_assets`.
- Update `app/db.py` migrations:
  - Add `prompt_snapshot_json` to `pipeline_runs` if missing.
  - Add any missing `generated_assets` columns needed by the current schema.
- Normalize pipeline asset types:
  - Existing old flow uses `highlight`, `promo`, `clip`.
  - Pipeline design names include `highlight_clip` and `promo_video`.
  - MVP can keep old public values for UI compatibility, but metadata should
    include the pipeline template key.
- Confirm `app/pipeline.py` can execute one `highlight_clip` run without
  throwing integration errors.
- Confirm `app/pipeline.py` can execute one `promo_single` run against one
  video, not the whole project list.

### Acceptance Criteria

- `python3 -m py_compile app/*.py` passes in `apps/highlight-service`.
- A direct backend pipeline run can create:
  - one `pipeline_runs` row,
  - multiple `pipeline_steps` rows,
  - `artifacts` rows,
  - final `generated_assets` rows with `pipeline_run_id`.
- Existing old endpoints still work.

### Verification

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-service
python3 -m py_compile app/*.py
```

Manual API checks after service start:

```bash
curl http://127.0.0.1:8765/api/health
curl http://127.0.0.1:8765/api/projects
```

## Phase 1: Official Pipeline API MVP

Goal: expose a stable HTTP contract for templates, runs, steps, artifacts, and
generated assets.

### Backend Tasks

- Add pipeline imports and routes to `apps/highlight-service/app/main.py`.
- Add request/response models in `app/models.py`:
  - `PipelineRunCreate`
    - `template_key: str`
    - `source_video_ids: list[int]`
    - `params: dict`
    - `prompt_template_ids: list[int]` or prompt key list if that is simpler.
  - Keep backward-compatible support for a single `source_video_id` during the
    migration if useful.
- Add routes:

```text
GET /api/pipeline-templates
GET /api/pipeline-templates/{template_key}
POST /api/projects/{project_id}/pipeline-runs
GET /api/projects/{project_id}/pipeline-runs
GET /api/pipeline-runs/{run_id}
GET /api/pipeline-runs/{run_id}/steps
GET /api/pipeline-runs/{run_id}/artifacts
GET /api/pipeline-runs/{run_id}/generated-assets
POST /api/pipeline-runs/{run_id}/cancel
```

- For `input_scope=single_video`, create one run per source video ID.
- Snapshot prompts at run creation time into `prompt_snapshot_json`.
- Add artifact listing helpers in `app/pipeline.py`.
- Add generated asset listing by run ID.
- Implement cancel as MVP state handling:
  - Cancel only `pending` runs immediately.
  - For synchronous running jobs, return a structured message if hard cancel is
    not yet possible.
- Keep templates hardcoded in Python for this phase. A database-backed
  `pipeline_templates` table can wait until template editing is needed.

### Acceptance Criteria

- Frontend can list templates before generation.
- Frontend can create runs from selected source videos.
- Backend returns run IDs and final run details.
- Run detail includes steps.
- Artifacts and generated assets can be fetched by run.
- Old `/api/highlights/auto/stream` and `/api/promos/generate/stream` still
  remain available during migration.

### Verification

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-service
python3 -m py_compile app/*.py
```

Manual API checks:

```bash
curl http://127.0.0.1:8765/api/pipeline-templates
curl http://127.0.0.1:8765/api/projects/1/pipeline-runs
```

## Phase 2: Processor And Template Cleanup

Goal: make pipeline behavior match the design and user expectation before
putting it at the center of the UI.

### Backend Tasks

- Make current templates explicit:

```text
highlight_clip:
  probe_video
  detect_highlight_candidates
  score_highlight_candidates
  render_highlight_clips

promo_single:
  probe_video
  plan_promo_single
  render_promo_single

promo_variants:
  probe_video
  plan_promo_variants
  render_promo_variants
```

- Add `promo_variants` as a first-class template if existing
  `generate_promo_video` already renders multiple variants.
- Ensure `promo_single` returns one final promo asset for one source video.
- Ensure `highlight_clip` returns many assets for one source video.
- Move template parameter normalization into pipeline processors:
  - `windows_per_video`
  - target duration or variant count when added.
- Ensure every processor writes useful `input_json` and `output_json`.
- Store AI trace data as artifacts where practical:
  - transcript,
  - model review,
  - keyframe review,
  - edit plan,
  - final render result.

### Acceptance Criteria

- A batch of three source videos creates three independent runs.
- One failed source video does not prevent other created runs from being
  inspectable.
- `promo_single` does not merge multiple videos into one output.
- `promo_variants` is the only template that intentionally produces multiple
  promo outputs from one source video.

### Verification

Use a small local project with two short videos:

```text
1. Upload or scan videos into one project.
2. Run highlight_clip for both videos.
3. Confirm two runs exist.
4. Confirm each run references one source_video_id.
5. Confirm generated assets are grouped by run and source video.
```

## Phase 3: Frontend Pipeline API Client And Types

Goal: add typed frontend access to the new API without disrupting the current
page.

### Frontend Tasks

- Add pipeline types in `src/types/dashboard.ts` or a new `src/types/pipeline.ts`:
  - `PipelineTemplate`
  - `PipelineRun`
  - `PipelineStep`
  - `PipelineArtifact`
  - `PipelineRunCreatePayload`
- Add service functions in `src/services/api.ts` or a new
  `src/services/pipeline.ts`:
  - `getPipelineTemplates`
  - `createPipelineRuns`
  - `getProjectPipelineRuns`
  - `getPipelineRun`
  - `getPipelineRunSteps`
  - `getPipelineRunArtifacts`
  - `getPipelineRunGeneratedAssets`
  - `cancelPipelineRun`
- Keep existing old generation service functions temporarily.
- Normalize API error display through existing `getErrorMessage`.

### Acceptance Criteria

- Frontend builds with new pipeline types and services.
- No visible UI behavior changes are required in this phase.

### Verification

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-cutter/frontend
pnpm build
```

## Phase 4: Project Detail Workflow UI

Goal: make the main UI reflect the project -> source videos -> pipeline runs ->
generated assets model.

### Frontend Tasks

- Keep `/` as the project workspace for now unless a dedicated route becomes
  necessary.
- Rework `src/pages/index.tsx` around project detail tabs:

```text
素材
生成流程
生成结果
发布
```

- Use Ant Design components only:
  - `Tabs`
  - `Table`
  - `Form`
  - `Select`
  - `Drawer`
  - `Timeline`
  - `Progress`
  - `Tag`
  - `Descriptions`
  - `Empty`
- Materials tab:
  - Project selector.
  - Upload and scan.
  - Source video table with multi-select.
- Generation tab:
  - Template selector from `GET /api/pipeline-templates`.
  - Dynamic basic params form from `params_schema`.
  - Selected source video list.
  - Start pipeline button.
  - Pipeline run table.
  - Run detail drawer with step timeline and artifacts.
- Generated Results tab:
  - Use `generated_assets`.
  - Group or filter by source video, template, and run.
  - Keep preview/download actions.
- Publish tab:
  - Initially show selectable generated assets.
  - Reuse existing publish service boundaries.
  - Defer real publish integration to Phase 6.

### Backend Dependency

This phase depends on Phase 1 APIs being available.

### Acceptance Criteria

- User can select a project.
- User can select one or more source videos.
- User can choose `highlight_clip`, `promo_single`, or `promo_variants`.
- User can start generation from the UI.
- User can see created runs and step statuses.
- User can see generated assets after the run.
- Old buttons are removed or clearly routed through pipeline templates.

### Verification

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-cutter/frontend
pnpm build
```

Browser checks:

```text
1. Open http://127.0.0.1:8001
2. Create/select a project.
3. Upload or scan a video.
4. Select one source video.
5. Run promo_single.
6. Open run detail and verify steps are visible.
7. Open generated results and verify the asset is visible.
8. Repeat with two selected videos and confirm two runs are created.
```

## Phase 5: Prompt Configuration Integration

Goal: connect the existing prompt settings page with pipeline runs.

### Backend Tasks

- Extend prompt configs with processor/template metadata if needed:
  - `processor_key`
  - `template_key`
  - or keep `category` plus key convention for MVP.
- Add a helper that returns prompts available for a template.
- At run creation:
  - resolve enabled prompt configs,
  - store `prompt_snapshot_json`,
  - pass snapshots through pipeline context.
- Ensure AI calls can use the snapshot for a run instead of always reading the
  latest prompt from `prompt_configs`.

### Frontend Tasks

- In Settings:
  - keep current prompt CRUD.
  - add visible association metadata if backend supports it.
- In Generation tab:
  - show which prompts will affect the selected template.
  - allow preview of prompt content.
  - optional MVP: do not allow per-run override yet, only snapshot enabled
    prompts.

### Acceptance Criteria

- Editing a prompt affects future runs.
- Existing runs keep their original prompt snapshot.
- Run detail can show prompt snapshot metadata.

### Verification

```text
1. Edit a prompt in Settings.
2. Start a pipeline run.
3. Confirm run detail includes the edited prompt snapshot.
4. Edit the prompt again.
5. Confirm old run detail still shows the old snapshot.
```

## Phase 6: Generated Asset Publish Flow

Goal: publish single generated assets and prepare project-level publish without
coupling frontend to upload internals.

### Frontend Tasks

- Add publish actions to generated asset rows:
  - Publish single asset.
  - Select assets for batch publish.
- Reuse `/publish-api` service functions from `src/services/publish.ts`.
- Do not import code from `apps/social-auto-upload`.

### Backend / Service Boundary Tasks

- Keep `highlight-service` as asset owner.
- Publish service should receive asset paths or asset IDs through HTTP.
- If publish service cannot resolve `asset_id`, the frontend can temporarily
  pass `output_path`, but the target contract should be asset-based.

### Acceptance Criteria

- A single generated asset can be sent to the publish flow.
- A project can select multiple generated assets for publish preparation.
- Publish failures show structured error messages.

### Verification

Use a local generated asset and a non-production account or dry-run path where
available. Real platform upload should not be treated as an automated test.

## Phase 7: Queue Worker

Goal: move long-running generation out of the request lifecycle while keeping
the same API and UI model.

### Backend Tasks

- Add a simple queue model:

```text
pipeline_jobs:
  id
  run_id
  status
  priority
  locked_by
  locked_at
  attempts
  error
  created_at
  updated_at
```

- Add worker command or service module:
  - pull pending jobs,
  - execute pipeline,
  - update run/step progress,
  - handle failures.
- Change create-run API:
  - create run,
  - create pending steps,
  - enqueue job,
  - return immediately.
- Add polling from frontend run table.
- Add cancel for pending jobs.

### Acceptance Criteria

- Creating a run returns quickly.
- Run table updates through polling.
- Worker can process pending runs.
- Failed runs store errors without breaking the API process.

### Verification

Backend:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-service
python3 -m py_compile app/*.py
```

Manual:

```text
1. Start API service.
2. Start worker.
3. Create a run from frontend.
4. Confirm run moves pending -> running -> succeeded/failed.
5. Stop worker and create a run.
6. Confirm run remains pending and UI shows pending state.
```

## Phase 8: Cleanup Compatibility Endpoints

Goal: remove duplicated old generation paths after the pipeline UI is stable.

### Backend Tasks

- Decide whether old endpoints become wrappers or are deprecated:
  - `/api/highlights/auto`
  - `/api/highlights/auto/stream`
  - `/api/promos/generate`
  - `/api/promos/generate/stream`
- If kept, implement them by creating pipeline runs internally.
- Remove duplicated generation logic from `app/main.py` only after the pipeline
  path covers existing behavior.

### Frontend Tasks

- Remove old generation calls from `src/services/api.ts`.
- Remove old mode-specific UI state if no longer used.
- Keep trace display components only if they are still used by run detail or
  artifact views.

### Acceptance Criteria

- There is one generation implementation path.
- Existing generated asset display still works.
- Project-based UI remains the primary workflow.

## Risk Register

### Long Synchronous Requests

Current generation can run for a long time. Phase 1 can tolerate synchronous
execution, but frontend should clearly show running state. Phase 7 should move
this to a worker.

### Prompt Snapshot Gap

Prompt CRUD exists, but pipeline runs do not yet snapshot prompts. Without this,
old run results become hard to explain after prompt edits.

### Existing Pipeline Integration Mismatch

`pipeline.py` and `projects.py` need to be reconciled before exposing pipeline
routes. Otherwise the first API call may fail when recording generated assets.

### Promo Semantics

Current promo generation can analyze multiple videos together. The target model
is one source video per run. Multi-video modes should only exist as explicit
future templates.

### Frontend Scope Creep

The current UI is already dense. Add pipeline views using Ant Design tables,
drawers, tabs, and existing layout components. Avoid adding a new UI library or
custom primitive set.

## Suggested Implementation Order

1. Phase 0: stabilize backend pipeline internals.
2. Phase 1: expose official pipeline APIs.
3. Phase 3: add frontend pipeline API client/types.
4. Phase 4: build project detail pipeline UI.
5. Phase 2: deepen processor/template correctness where needed during UI
   integration.
6. Phase 5: prompt snapshot integration.
7. Phase 6: generated asset publish flow.
8. Phase 7: queue worker.
9. Phase 8: cleanup old endpoints.

Phase 2 can partially overlap with Phases 1 and 4, but `promo_single` one-video
semantics should be fixed before the UI makes it a primary mode.

## Definition Of Done For MVP

The pipeline MVP is done when:

- A user creates or selects a short-drama project.
- A user uploads or scans source videos into that project.
- A user selects one or more source videos.
- A user selects a pipeline template.
- Backend creates one run per selected source video for single-video templates.
- Each run persists steps, artifacts, status, progress, and final generated
  assets.
- Frontend shows run history and step detail.
- Frontend shows generated assets grouped under the project.
- A generated asset can be selected for publishing.
- Prompt edits affect future runs, and run prompt snapshots preserve historical
  context.
