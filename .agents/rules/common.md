# Common Rules

## Working Style

- Treat this directory as colocated independent projects, not a single package workspace.
- Keep edits scoped to the service or frontend area requested.
- Preserve user changes and runtime state. Do not reset, revert, delete, or overwrite unrelated files.
- Prefer existing patterns in the target subproject over adding new abstractions.
- Avoid broad refactors unless the user explicitly asks for them.

## Files To Avoid

Do not edit generated, dependency, cache, or runtime files unless explicitly asked:

- `**/node_modules/**`
- `**/.venv/**`
- `**/__pycache__/**`
- `**/.pytest_cache/**`
- `apps/highlight-cutter/frontend/src/.umi/**`
- `apps/highlight-cutter/frontend/src/.umi-production/**`
- `**/dist/**`
- `logs/**`
- `garden-gpt-image-2/image/**`
- `apps/highlight-service/data/**`, `inputs/**`, `outputs/**`, `work/**`
- `apps/social-auto-upload/cookies/**`, `logs/**`, `videos/**`, `media/**`, `db/*.db`

## Dependency Rules

- Do not add a new frontend UI library without explicit user approval.
- Do not add backend dependencies unless they are required for the requested change and the target service environment is clear.
- If a command fails because a dependency is missing, report the exact missing dependency and the command used. Install only when doing so is necessary to complete the requested task.

## Documentation

- Keep root-level planning and status information in `README.md` and `PROJECT_STATUS.md`.
- Update these instructions if service boundaries, ports, or startup commands change.
