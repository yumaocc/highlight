# Story Quality Cut Workspec

## Goal

Add a short-drama quality cut mode that removes low-value footage and keeps all
useful story material.

This is different from a promo edit. The output does not target a fixed runtime.
The model should preserve story quality, continuity, character relationships,
conflict setup, reversals, emotional beats, and cliffhangers. Runtime is a
result, not the primary constraint.

## Product Mode

- Template key: `story_quality_cut`
- Display name: `剧情精剪`
- Input: multiple source videos in one short-drama project
- Output: one edited video asset
- Run strategy: `aggregate`
- Ordering: preserve original episode/time order by default

## Decision Policy

The model/edit logic should classify timeline sections as:

- `keep_required`: required for story understanding or dramatic payoff.
- `keep_optional`: useful reaction, mood, or transition material.
- `drop`: repeated, low-information, poor-quality, or non-progressing footage.

The renderer should keep:

- `strict`: only `keep_required`.
- `balanced`: `keep_required` plus useful `keep_optional`.
- `loose`: all non-drop material unless it harms pacing.

## MVP Implementation

The first implementation uses the existing pipeline foundation, proxy video
generation, and local candidate discovery:

1. `create_proxy_videos`
2. `model_watch_quality_cut`
3. `validate_quality_edit_decisions`
4. `render_story_quality_cut`

MVP behavior:

- Create one aggregate run for selected source videos.
- Store all selected source videos in `pipeline_run_sources`.
- Generate low-resolution proxy videos for model-friendly review.
- Ask the multimodal model to produce keep/drop decisions from proxy videos.
- Validate and normalize timestamped model decisions.
- Render the kept windows from the original files.
- Record one generated asset for the quality cut.

## Future Direction

Improve proxy-video model review:

1. Add chunked review for long episodes or large proxy files.
2. Add transcript/keyframe artifacts next to proxy videos.
3. Add stricter continuity checks for visual conflict and dialogue truncation.

Proxy videos should preserve source duration and timestamps so model decisions
map back to the original files for final rendering.
