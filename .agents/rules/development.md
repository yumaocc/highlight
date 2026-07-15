# Development Rules

## Frontend Rules

- Use Ant Design components for UI controls, layout primitives, forms, tables, lists, collapse panels, upload controls, buttons, menus, tags, alerts, and empty states.
- Reuse local components from `apps/highlight-cutter/frontend/src/components` before creating new components.
- If neither Ant Design nor the existing local components provide the required component, ask the user for secondary confirmation before building a custom UI primitive or adding a new UI library.
- Keep page files focused on workflow/state orchestration. Put reusable UI in `src/components`.
- Keep HTTP calls in `src/services/*`; do not call `fetch` directly from new components unless matching an existing service helper is impractical.
- Keep shared frontend types in `src/types`.
- Follow current import aliases such as `@/components/...`, `@/services/...`, and `@/types/...`.
- Match the existing operational dashboard style in `src/global.css`: compact, light, Ant Design-compatible, 8px radius, restrained teal accent.
- For workflow pages, prioritize upload/actions, model output, generated assets, task progress, and clear empty/error/loading states.
- Do not revive the old FastAPI static frontend coupling. Frontend build output belongs in `apps/highlight-cutter/frontend/dist`.

Representative frontend files to inspect before similar edits:

- `src/pages/index.tsx`
- `src/components/layout/WorkspaceLayout.tsx`
- `src/components/dashboard/WorkbenchHero.tsx`
- `src/components/dashboard/ModelOutputPanel.tsx`
- `src/components/trace/TraceChat.tsx`
- `src/services/api.ts`
- `src/services/publish.ts`

## Backend Rules

- Keep `apps/highlight-service` independent from frontend code and from `social-auto-upload` internals.
- Add FastAPI routes in `app/main.py` only when they belong to the highlight service.
- Keep configuration and runtime paths in `app/config.py`; do not hardcode project-local output paths in route handlers if a settings property exists.
- Use existing helpers for database access, video discovery/probing/cutting, AI enrichment, and promo generation.
- Return structured JSON errors/details that the frontend can display.
- Do not print or expose `.env` secrets.

Representative backend files to inspect before similar edits:

- `apps/highlight-service/app/main.py`
- `apps/highlight-service/app/config.py`
- `apps/highlight-service/app/db.py`
- `apps/highlight-service/app/ffmpeg.py`
- `apps/highlight-service/app/promo_pipeline.py`

## Social Upload Rules

- Treat `apps/social-auto-upload` as a legacy/upstream capability source unless the task is specifically about that project.
- Prefer wrapping its CLI/uploader capabilities behind a future service API rather than making the main console depend on its internal modules directly.
- Its legacy Flask backend depends on local database initialization; if account APIs fail with missing tables, initialize or inspect `apps/social-auto-upload/db/createTable.py` rather than masking the error in the frontend.
