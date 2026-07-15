# Short Drama Pipeline Design

## Purpose

This document defines the next architecture direction for `highlight-service`
and the console UI.

The system should no longer treat generation as an isolated action on one
screen. A short-drama project owns source videos, source videos flow through
processing pipelines, every processing step writes its result, and final
generated assets can be published individually or as part of the whole project.

Core shape:

```text
Project
  SourceVideo[]
    -> PipelineRun
      -> PipelineStep[]
        -> Artifact[]
        -> GeneratedAsset[]
```

The input unit is a single `SourceVideo` by default. A project can contain many
videos, and the same video can enter different pipeline templates.

## Goals

- Use a project as the main product unit, not an isolated video task.
- Keep every source video independently processable.
- Support extensible generation modes around two main product shapes:
  - `many -> one`: multiple source videos are processed into one final work.
  - `x -> x`: X source videos each produce one corresponding final work.
  - `promo_single`: one source video produces one drainage/promo work.
  - `promo_variants`: multiple source videos each produce one corresponding
    promo variant set only when the template explicitly asks for variants.
  - Future modes such as covers, subtitles, publish copy, platform-specific
    versions, and review packages.
- Store intermediate and final results so later UI can inspect what happened.
- Make each step observable with status, progress, inputs, outputs, and errors.
- Allow the same pipeline model to run synchronously at first and move to a
  queue/worker model later.
- Keep frontend and backend connected through HTTP APIs only.

## Non-Goals For MVP

- Rollback. Regeneration is acceptable if a run fails or the user changes
  configuration.
- Artifact cache or reuse across runs.
- Distributed workers.
- Complex DAG scheduling.
- Resume from an arbitrary failed step.
- Multi-source merge as the default behavior.

These can be added later, but they should not complicate the first pipeline
implementation.

## Core Concepts

### Project

A short-drama project is the top-level business object. It groups source
materials, generation runs, generated assets, and publish state.

Examples:

- A single episode project.
- A batch of source videos for the same drama.
- A campaign containing several generated promo assets.

### SourceVideo

A source video is an original material file inside a project.

Pipeline processing normally starts from one `SourceVideo`. Even when the UI
starts a batch operation, the backend should create one pipeline run per source
video unless a future template explicitly declares multi-source input.

### PipelineTemplate

A pipeline template defines a reusable processing mode.

It describes:

- Which processors run.
- The order of processors.
- Input scope.
- Output cardinality.
- User-configurable parameters.
- Required prompt templates or prompt groups.

Templates are the extension point for new modes. Adding a mode should usually
mean adding a template and one or more processors, not rewriting route handlers.

### Processor

A processor is one concrete processing unit. It receives a normalized context,
reads previous artifacts, performs one transformation, writes artifacts, and
returns structured output.

Examples:

- Probe video metadata.
- Extract audio.
- Transcribe speech.
- Detect candidate highlight segments.
- Score segments.
- Plan promo structure.
- Render final video.
- Generate publish copy.

### PipelineRun

A pipeline run is one execution of one template against one source video inside
one project.

It records:

- Selected template.
- Runtime parameters.
- Prompt snapshots.
- Overall status.
- Progress.
- Current step.
- Final result summary.
- Error details if failed.

### PipelineStep

A pipeline step is one processor execution inside a run.

It records:

- Step key and display name.
- Order.
- Status and progress.
- Input snapshot.
- Output snapshot.
- Error details.
- Start and finish times.

### Artifact

An artifact is any intermediate or final step result.

Examples:

- Probe metadata JSON.
- Audio file.
- Transcript JSON.
- Keyframe images.
- Candidate segment list.
- Prompt output.
- Rendered video file.

Artifacts are primarily for traceability and future UI inspection.

### GeneratedAsset

A generated asset is a final user-facing output that can be downloaded,
previewed, selected, or published.

Examples:

- One highlight clip.
- One promo video.
- A set of promo variants.
- Cover images.
- Platform-specific video versions.
- Publish title, description, and tags.

## Proposed Data Model

The exact storage can remain SQLite for the current local product. JSON columns
can be stored as text in SQLite and parsed by service helpers.

### `projects`

Project table already exists or should become the central owner of video assets.

Important fields:

```text
id
name
description
status
metadata_json
created_at
updated_at
```

### `source_videos`

Original materials owned by a project.

```text
id
project_id
filename
original_path
stored_path
duration
width
height
fps
status
metadata_json
created_at
updated_at
```

### `pipeline_templates`

Registered generation modes.

```text
id
key
name
description
input_scope              # single_video | multi_video | project
output_cardinality       # one | many
steps_json
params_schema_json
default_params_json
enabled
created_at
updated_at
```

`input_scope` should start with `single_video`. `multi_video` and `project`
are reserved for later modes that intentionally need multiple source videos.

### `pipeline_runs`

One template execution against one input scope.

```text
id
project_id
source_video_id          # nullable only for future project/multi-video runs
template_key
status                   # pending | running | succeeded | failed | canceled
current_step
progress
params_json
prompt_snapshot_json
result_json
error
created_at
started_at
finished_at
updated_at
```

### `pipeline_steps`

Processor execution records.

```text
id
run_id
project_id
source_video_id
step_key
name
order_index
status                   # pending | running | succeeded | failed | skipped
progress
input_json
output_json
error
created_at
started_at
finished_at
updated_at
```

### `artifacts`

Step outputs and trace files.

```text
id
project_id
source_video_id
run_id
step_id
type                     # metadata | audio | transcript | keyframes | plan | video | copy
path
content_json
metadata_json
is_final
created_at
```

Use `path` for files and `content_json` for structured in-database content.
Both can exist for the same artifact.

### `generated_assets`

Final outputs shown to the user and passed to publish APIs.

```text
id
project_id
source_video_id
run_id
step_id
type                     # highlight_clip | promo_video | cover | copy | platform_package
title
description
output_path
download_url
duration
width
height
metadata_json
publish_status
created_at
updated_at
```

Publishing should consume `GeneratedAsset` records instead of ad hoc file paths
once this model is in place.

## Processor Contract

Processors should share a small interface so pipeline templates can compose
them.

Conceptual contract:

```text
Processor:
  key: string
  name: string
  input_types: string[]
  output_types: string[]
  params_schema: object
  execute(context) -> ProcessorResult
```

Context should include:

```text
project
source_video
pipeline_run
pipeline_step
params
prompt_snapshots
previous_artifacts
workspace_paths
```

Result should include:

```text
status
progress
artifacts
generated_assets
output_json
logs
```

Processors should not directly decide UI behavior. They should return
structured records that routes and frontend services can display.

## Initial Processor Set

Start by wrapping existing backend capabilities into processors:

```text
probe_video
extract_audio
transcribe_audio
extract_keyframes
detect_candidates
score_candidates
plan_highlight_clips
plan_promo_single
plan_promo_variants
render_clips
render_promo
generate_publish_copy
```

Additional processors can be added later:

```text
extract_cover_candidates
render_cover
burn_subtitles
platform_resize
platform_metadata_package
human_review_gate
quality_check
```

## Pipeline Templates

### `highlight_clip`

Purpose: extract highlight material from one source video. This is an
intermediate material-producing template, not a product-level "choose N clips"
mode.

```text
probe_video
extract_audio
detect_candidates
transcribe_audio
extract_keyframes
score_candidates
plan_highlight_clips
render_clips
```

Input:

```text
single SourceVideo
```

Output:

```text
GeneratedAsset(type=highlight_clip) records based on detected highlight material
```

### `promo_single`

Purpose: generate one drainage/promo video from one source video.

```text
probe_video
extract_audio
transcribe_audio
extract_keyframes
detect_candidates
score_candidates
plan_promo_single
render_promo
generate_publish_copy
```

Input:

```text
single SourceVideo
```

Output:

```text
one GeneratedAsset(type=promo_video)
optional GeneratedAsset(type=copy)
```

### `promo_variants`

Purpose: generate multiple promo variants from one source video.

```text
probe_video
extract_audio
transcribe_audio
extract_keyframes
detect_candidates
score_candidates
plan_promo_variants
render_promo
generate_publish_copy
```

Input:

```text
single SourceVideo
```

Output:

```text
many GeneratedAsset(type=promo_video)
many optional GeneratedAsset(type=copy)
```

### Future Multi-Source Templates

The model can support multi-source modes later, but those should be explicit
templates with `input_scope=multi_video`.

Examples:

```text
project_recap
multi_episode_best_of
campaign_package
```

They should not change the default rule: normal processing is one source video
entering one pipeline run.

## Prompt Configuration

Prompts should be configured from the frontend and stored in the backend, not
hardcoded in backend local functions.

Recommended prompt model:

```text
prompt_templates:
  id
  key
  name
  description
  processor_key
  content
  variables_schema_json
  enabled
  created_at
  updated_at
```

Pipeline runs should store `prompt_snapshot_json`. This prevents old runs from
changing meaning after the user edits a prompt template.

Prompt selection should happen at run creation time:

```text
template + params + selected prompt templates -> prompt snapshot
```

## API Design

### Template APIs

```text
GET /api/pipeline-templates
GET /api/pipeline-templates/{template_key}
```

Optional admin APIs when templates become configurable:

```text
POST /api/pipeline-templates
PUT /api/pipeline-templates/{template_key}
DELETE /api/pipeline-templates/{template_key}
```

### Run APIs

Create one or more runs from a project page:

```text
POST /api/projects/{project_id}/pipeline-runs
```

Request:

```json
{
  "template_key": "promo_single",
  "source_video_ids": ["video_1", "video_2"],
  "params": {},
  "prompt_template_ids": []
}
```

Behavior:

- For `input_scope=single_video`, create one run per `source_video_id`.
- Return created run IDs.
- Start immediately for MVP or enqueue for the future worker model.

List and inspect runs:

```text
GET /api/projects/{project_id}/pipeline-runs
GET /api/pipeline-runs/{run_id}
GET /api/pipeline-runs/{run_id}/steps
GET /api/pipeline-runs/{run_id}/artifacts
GET /api/pipeline-runs/{run_id}/generated-assets
POST /api/pipeline-runs/{run_id}/cancel
```

### Asset APIs

```text
GET /api/projects/{project_id}/generated-assets
GET /api/generated-assets/{asset_id}
GET /api/generated-assets/{asset_id}/download
```

Publishing should accept assets:

```text
POST /publish-api/publish-tasks
```

Request shape direction:

```json
{
  "asset_ids": ["asset_1"],
  "platform": "douyin",
  "account_id": "account_1",
  "publish_params": {}
}
```

Project-level publish should also be supported:

```text
POST /api/projects/{project_id}/publish
```

This can collect selected or eligible `GeneratedAsset` records and create
publish tasks through the publish service.

## Execution Model

### MVP: Synchronous Service Execution

The first implementation can run a pipeline inside the API process if that is
the fastest path.

Required behavior:

- Create `pipeline_run`.
- Create all `pipeline_steps` as pending.
- Mark each step running before execution.
- Write artifacts and generated assets after each step.
- Mark step succeeded or failed.
- Update run progress and current step.
- Mark run succeeded or failed.

Even if execution is synchronous, the persisted run/step model should look the
same as the future queued model.

### Future: Queue And Worker Execution

The pipeline model should be compatible with a queue:

```text
API creates run -> enqueue run/step -> worker executes -> DB stores progress
```

Queue-ready fields:

```text
status
current_step
progress
started_at
finished_at
error
```

Potential future worker features:

- Concurrency limit.
- GPU/CPU resource tags.
- Per-template priority.
- Cancel pending/running work.
- Worker heartbeat.
- Step timeout.

## Frontend UX

The console should be organized around projects.

### Project List

Show all short-drama projects:

- Name.
- Source video count.
- Generated asset count.
- Running/failed pipeline count.
- Publish status summary.

Primary actions:

- Create project.
- Open project.
- Publish project.

### Project Detail

Recommended tabs:

```text
素材
生成流程
生成结果
发布
设置
```

### Materials Tab

Show source videos in the project.

Actions:

- Upload or scan videos.
- View metadata.
- Select one or more source videos.
- Start a pipeline from selected source videos.

### Generation Flow Tab

Show pipeline templates and runs.

Start-run form:

- Select source videos.
- Select generation template.
- Configure template params.
- Select or preview prompt templates.
- Start generation.

Run list:

- Template name.
- Source video.
- Status.
- Progress.
- Current step.
- Created time.
- Error summary.

Run detail:

- Step timeline.
- Step input/output summary.
- Artifacts.
- Generated assets.
- Logs/errors.

### Generated Results Tab

Show final assets grouped by source video and pipeline run.

Actions:

- Preview.
- Download.
- Rename/title edit.
- Select for publishing.
- Publish single asset.
- Add to project publish batch.

### Publish Tab

Publish should work at two levels:

- Publish a single generated asset.
- Publish a selected batch or whole project.

The publish service should not need to know how a video was generated. It
should receive generated assets and publish params.

## Extension Points

The current design intentionally keeps these areas extensible:

- Pipeline templates: add a mode without changing the project model.
- Processors: wrap new media, AI, rendering, or publishing preparation logic.
- Prompt templates: configure AI behavior from the frontend.
- Generated asset types: support videos, covers, copy, subtitle files, and
  platform packages.
- Input scope: start with `single_video`, later add explicit `multi_video` or
  `project` templates.
- Execution: start synchronous, move to queued workers without changing the UI
  contract.
- Publish integration: publish assets through HTTP APIs instead of direct code
  coupling.
- Human review: add review-gate processors later when needed.
- Resource policy: add processor-level tags for CPU/GPU/model-heavy work.

## Implementation Phases

### Phase 1: Design, Schema, API Skeleton

- Add project/source-video/pipeline terminology to docs.
- Add database tables or migrations for templates, runs, steps, artifacts, and
  generated assets.
- Add read APIs for templates and runs.
- Add create-run API with persisted run records.
- Keep execution minimal.

### Phase 2: Wrap Existing Generation As Pipelines

- Wrap existing highlight generation as `highlight_clip`.
- Wrap existing promo generation as `promo_single`.
- Store existing outputs as `GeneratedAsset`.
- Store important intermediate outputs as `Artifact`.
- Snapshot prompt templates when a run starts.

### Phase 3: Frontend Project Workflow

- Move UI focus to project detail pages.
- Add source video selection.
- Add pipeline template selection.
- Add run list and step detail views.
- Add generated asset gallery/list.
- Add single-asset publish action.

### Phase 4: Queue Worker

- Introduce a queue table or lightweight worker process.
- Let API create runs and enqueue work.
- Let worker update step/run progress.
- Add cancel for pending work first, then running work if practical.

### Phase 5: Publish And Operations Maturity

- Publish individual generated assets.
- Publish selected project assets in batch.
- Add platform-specific packaging processors.
- Add resource limits.
- Add human review gates.
- Add richer run logs and error categories.

## Key Product Decisions

- The short-drama project is the main product unit.
- Product modes should primarily be either multiple source videos combined into
  one work, or X source videos producing X final works.
- Batch operation means creating one run per source video unless a template
  explicitly declares a many-source input scope.
- Pipeline templates are the main extension mechanism for future modes.
- Queue execution is part of the direction, but the MVP can run synchronously if
  it persists the same run and step state.
- Rollback and artifact reuse are intentionally excluded from the MVP.
