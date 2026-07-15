# Pipeline Task Tracker

This file tracks implementation status for the short-drama project pipeline.

Status legend:

- `done`: implemented and verified enough for the current phase.
- `in_progress`: partially implemented, still needs follow-up work.
- `pending`: not implemented yet.
- `blocked`: cannot continue without a decision, dependency, or runtime state.

## 1. Design And Planning

| Status | Task | Notes |
| --- | --- | --- |
| done | Write pipeline architecture design | See `docs/PIPELINE_DESIGN.md`. |
| done | Write repository-aware development plan | See `docs/PIPELINE_DEVELOPMENT_PLAN.md`. |
| done | Create implementation log | See `docs/PIPELINE_IMPLEMENTATION_LOG.md`. |
| done | Create task tracker | This file. |

## 2. Backend Foundation

| Status | Task | Notes |
| --- | --- | --- |
| done | Add project-level model foundation | `projects` table and project CRUD already exist. |
| done | Add generated asset model foundation | `generated_assets` table and asset listing already exist. |
| done | Add prompt CRUD foundation | `prompt_configs` table and prompt APIs already exist. |
| done | Add pipeline tables | `pipeline_runs`, `pipeline_steps`, and `artifacts` exist. |
| done | Add `prompt_snapshot_json` to runs | Added to schema and migration. |
| done | Allow generated assets to store `pipeline_run_id` | Added to `record_generated_asset`. |
| done | Allow generated assets to store `pipeline_step_id` | Added to `record_generated_asset`. |
| done | Expand pipeline run create payload | Supports `source_video_ids`, compatibility `source_video_id`, `params`, and `prompt_config_ids`. |
| in_progress | Normalize source video terminology | Backend table is still named `videos`; design calls it `SourceVideo`. Naming can stay for now, but docs/UI should consistently present it as source material. |
| pending | Add database-backed `pipeline_templates` table | Current templates are hardcoded in `app/pipeline.py`; acceptable for MVP. |

## 3. Backend Pipeline APIs

| Status | Task | Notes |
| --- | --- | --- |
| done | List pipeline templates | `GET /api/pipeline-templates`. |
| done | Get one pipeline template | `GET /api/pipeline-templates/{template_key}`. |
| done | Create project pipeline runs | `POST /api/projects/{project_id}/pipeline-runs`. |
| done | Create one run per selected source video | Implemented for `source_video_ids`. |
| done | List project pipeline runs | `GET /api/projects/{project_id}/pipeline-runs`. |
| done | Get pipeline run detail | `GET /api/pipeline-runs/{run_id}`. |
| done | List pipeline steps | `GET /api/pipeline-runs/{run_id}/steps`. |
| done | List pipeline artifacts | `GET /api/pipeline-runs/{run_id}/artifacts`. |
| done | List generated assets by run | `GET /api/pipeline-runs/{run_id}/generated-assets`. |
| in_progress | Cancel pipeline runs | Pending runs can be canceled; running synchronous runs cannot be interrupted yet. |
| done | Add queued execution APIs | Added pipeline job list and run-next APIs plus enqueue mode on run creation. |

## 4. Backend Processors And Templates

| Status | Task | Notes |
| --- | --- | --- |
| done | Add processor abstraction | Basic `Processor` wrapper exists in `app/pipeline.py`. |
| done | Add `highlight_clip` template | Existing template: one source video to many highlight assets. |
| done | Add `promo_single` template | Existing template: one source video to promo output path. Needs real-video validation. |
| done | Add `promo_variants` template | Added as one source video to many promo versions. |
| pending | Add explicit `1 -> 1` generic template metadata | Current `promo_single` covers it, but template metadata should make the cardinality obvious in UI. |
| done | Add generic run strategy metadata | Templates now declare `per_source` or `aggregate` creation behavior. |
| done | Add multi-source run binding | Added `pipeline_run_sources` for aggregate/multi-source pipeline runs. |
| done | Add `story_promo_mix` template | Added `剧情引流总剪` as multi-video to one aggregate promo output. |
| done | Add `story_quality_cut` MVP template | Added `剧情精剪` as multi-video to one aggregate quality-cut output. Current planning uses local candidate windows. |
| done | Add proxy video generation step for `story_quality_cut` | First step now creates low-resolution proxy videos under `work/proxy/run_{run_id}`. |
| done | Remove meaningless highlight max-count param | Removed `最多片段数` from `highlight_clip`; product modes should not be driven by arbitrary clip count. |
| pending | Add product-mode params | Need target duration, platform style, hook strength, and whether mode is `many -> one` or `x -> x`. |
| pending | Add future extension template placeholders | Example: cover extraction, subtitles, platform package, publish copy. |
| in_progress | Persist step artifacts | Basic step output artifacts are stored. |
| in_progress | Persist fine-grained AI artifacts | `story_quality_cut` stores proxy review and validated decisions as step artifacts; transcript/keyframes/GPT draft remain pending for other flows. |
| pending | Add two-stage story aggregation | `story_promo_mix` currently reuses existing promo generation; next step is per-episode summaries then project-level edit planning. |
| done | Add proxy-video model review for `story_quality_cut` | Added Gemini proxy-video review and validated timestamped keep/drop decisions. Needs real API E2E validation. |
| done | Add quality-cut decision validation | Model decisions are bounded to source duration, invalid rows are rejected, adjacent same-label segments are merged, short keep fragments are filtered, short keep gaps are bridged, and rendering consumes validated kept segments. |
| done | Drop source-video built-in outros in `story_quality_cut` | Updated the editable `story_quality_cut_review` prompt and Gemini review payload to identify and drop source endings such as 未完待续, 看全集 CTA, platform end cards, black/frozen ending screens, credits, and end titles. |
| done | Make final-video intro/outro explicit and mandatory | Added `generate_review_cover` and `generate_outro_cta` steps to promo/story pipelines; final renders concatenate those segments and fall back to text cards if image generation fails. |
| pending | Make AI clients use run prompt snapshots | Runs store snapshots, but most AI calls still read current enabled prompts. |

## 5. Frontend API And Types

| Status | Task | Notes |
| --- | --- | --- |
| done | Add pipeline frontend types | Added `PipelineTemplate`, `PipelineRun`, `PipelineStep`, `PipelineArtifact`, `PipelineRunCreatePayload`. |
| done | Add pipeline API client functions | Added functions in `src/services/api.ts`. |
| done | Keep old generation API clients during migration | Old stream functions still exist. |
| pending | Split pipeline API into `src/services/pipeline.ts` | Optional cleanup once usage grows. |

## 6. Frontend Project Workflow

| Status | Task | Notes |
| --- | --- | --- |
| done | Keep project selector on main page | Existing behavior preserved. |
| done | Add project list and delete action | Main short-drama page now has a project list drawer with switch/delete actions; deletion is guarded against active pipeline tasks and preserves exported outputs. |
| done | Upload source material by folder | Materials tab now supports selecting a video folder and filters supported video files before upload. |
| done | Auto-open source list when videos exist | Prevents uploaded videos from being hidden behind a collapsed material list. |
| done | Add pipeline generation panel | `PipelineFlowCard` added to main dashboard. |
| done | Load pipeline templates in frontend | Main page calls `getPipelineTemplates`. |
| done | Select multiple source videos for pipeline | Implemented in `PipelineFlowCard`. |
| done | Batch select pipeline source videos | Added selected count, `全选`, and `清空` controls. |
| done | Show aggregate task count | Multi-source templates show that selected sources create one total-edit task. |
| done | Render select-type template params | `剧情精剪` keep policy is rendered as an Ant Design select. |
| done | Start pipeline runs from frontend | Calls `createPipelineRuns`. |
| done | Show pipeline run history | Run table exists in `PipelineFlowCard`. |
| done | Show run detail drawer | Displays run metadata, step timeline, and artifacts. |
| done | Enforce project id on detail fetches | Frontend passes selected project id; backend returns 404 when video/run detail does not belong to that project. |
| in_progress | Refresh project assets after pipeline run | Implemented after run completion; needs browser validation with real generated files. |
| done | Replace old generation buttons | `WorkbenchHero` generation buttons now create pipeline runs for `highlight_clip` and `promo_single`. |
| done | Remove generation controls from materials tab | Materials tab now only handles source upload/listing; generation starts from the generation flow tab. |
| in_progress | Restructure page into project tabs | Main page now has materials, generation flow, generated results, and process log tabs. Publish/settings are still separate. |
| done | Add generated asset grouping by run/template/source video | Asset panel now filters by type, source video, and pipeline run, and displays pipeline metadata. |
| in_progress | Add artifact detail preview | `剧情精剪` now shows review summary, risks, per-source keep ratio, decisions, and rejected rows. Generic artifact JSON preview remains pending. |
| done | Add prompt snapshot display in run detail | Run detail drawer now shows prompt snapshot key/name/content summary. |

## 7. Queue And Long-Running Execution

| Status | Task | Notes |
| --- | --- | --- |
| done | Add queue/job table | Added `pipeline_jobs`. |
| done | Add worker process | Added `.venv/bin/python -m app.worker` with loop mode and `--once`. |
| done | Change create-run API to enqueue work | `POST /api/projects/{project_id}/pipeline-runs?enqueue=true` creates pending jobs; default remains synchronous. |
| done | Add frontend polling | Frontend polls runs/assets while pending or running runs exist. |
| done | Support cancel pending jobs | Canceling a pending run also marks its pending job canceled. |
| pending | Support running cancellation where practical | Requires worker cooperation and processor-level cancellation checks. |
| pending | Add resource controls | CPU/GPU/model-heavy concurrency limits. |

## 8. Publishing

| Status | Task | Notes |
| --- | --- | --- |
| done | Publish a single generated asset | Generated asset rows link to `/publish` with project and asset query params. |
| done | Publish selected project assets | Asset panel supports selecting multiple generated assets and opening publish form prefilled. |
| done | Generate publish tags with promo copy | Generated assets now include normalized `#文字内容` tags, always including `#快来看短剧`; publish page auto-fills selected asset tags. |
| pending | Publish whole short-drama project | Needs project-level eligibility rules and selected assets. |
| pending | Store publish task linkage | Generated assets should record publish task/status when available. |
| pending | Avoid direct coupling to `social-auto-upload` internals | Must remain HTTP API based. |

## 9. Compatibility And Cleanup

| Status | Task | Notes |
| --- | --- | --- |
| in_progress | Convert old highlight endpoint to pipeline wrapper | Frontend no longer uses old highlight generation button path, but backend endpoints still contain separate logic. |
| in_progress | Convert old promo endpoint to pipeline wrapper | Frontend no longer uses old promo generation button path, but backend endpoints still contain separate logic. |
| pending | Remove duplicated generation code | Only after pipeline UI is validated. |
| pending | Project-scope download endpoints | Generated asset lists are project-scoped, but raw clip/promo download URLs are still global. |
| in_progress | Project-scope runtime output paths | `story_quality_cut` uses run-specific output filenames; older promo processors still have shared output risk. |
| pending | Decide old trace UI future | Existing trace components may become artifact/run detail views or be removed. |
| pending | Rename UI language from high-light cutter to short-drama pipeline where needed | Current branding still says `高光剪辑` in places. |

## 10. Validation

| Status | Task | Notes |
| --- | --- | --- |
| done | Backend syntax check | Passed with `PYTHONPYCACHEPREFIX=/private/tmp/highlight-pycache`. |
| done | Backend import check | Passed with `.venv/bin/python`. |
| done | Frontend build | `pnpm build` passed. |
| done | New API smoke check on fresh backend | Passed on temporary port `8766`. |
| in_progress | Browser UI check against current `8765` service | `8765` was restarted and frontend proxy returns pipeline templates. Chrome MCP visual check is blocked by an existing browser profile lock. |
| pending | End-to-end run with real source video | Needs restarted service and sample/real video. |
| pending | Verify one selected video creates one run | Needs E2E run. |
| pending | Verify multiple selected videos create multiple runs | Needs E2E run. |
| pending | Verify generated assets link back to pipeline run | Needs E2E run. |

## Next Execution Order

1. Restart local `highlight-service` so `8765` loads the new pipeline routes.
2. Browser-check the main dashboard and pipeline panel.
3. Run `highlight_clip` with one real source video.
4. Run `highlight_clip` with multiple selected source videos.
5. Fix any backend or UI issues found during E2E validation.
6. Add `promo_variants` as a first-class template.
7. Replace old generation buttons with pipeline-template actions.
8. Restructure the main page into project tabs.
9. Add queue/worker execution.
10. Add generated asset publish flow.
