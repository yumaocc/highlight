# API Contract Rules

## Service Boundaries

- The console frontend calls backends through HTTP APIs only.
- `highlight-service` owns video upload, scan, clip generation, AI trace data, and generated highlight/promo files.
- Publish/account/upload-platform behavior should be exposed through a publish service API. Do not make console UI import Python code from `apps/social-auto-upload`.
- Keep frontend proxy paths stable unless the user asks for a service boundary change:
  - `/api` for highlight-service.
  - `/publish-api` for publish-service or legacy social upload backend adapter.

## Frontend API Clients

- Add or update API calls in:
  - `apps/highlight-cutter/frontend/src/services/api.ts`
  - `apps/highlight-cutter/frontend/src/services/upload.ts`
  - `apps/highlight-cutter/frontend/src/services/publish.ts`
- Update TypeScript types in `src/types` or the relevant service file when response shapes change.
- Keep UI components consuming typed service functions rather than hardcoded URLs.

## Highlight Service API

Current important endpoints live in `apps/highlight-service/app/main.py`:

- `GET /api/health`
- `POST /api/upload`
- `POST /api/scan`
- `GET /api/videos`
- `DELETE /api/videos`
- `POST /api/highlights/auto`
- `POST /api/promos/generate`
- clip and promo download endpoints

When changing response fields, update frontend consumers in the same task.

## Publish API Direction

The planned publish service should provide stable JSON APIs for:

- platforms and capabilities
- accounts and login status
- login flow initiation
- video publish task creation
- task list/detail/progress/logs

Until a dedicated `publish-service` exists, mark publish API behavior as provisional and avoid overfitting the console to `sau_backend.py` quirks.

## Errors And Long Tasks

- Long-running generation/upload operations should expose progress or structured status when possible.
- Frontend error display should use existing error helpers such as `src/utils/errors.ts`.
- Do not hide backend errors that indicate missing database initialization, missing dependencies, invalid cookies, or platform login failures.
