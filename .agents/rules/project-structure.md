# Project Structure

## Root

- `README.md`: user-facing startup summary.
- `PROJECT_STATUS.md`: current architecture and roadmap notes.
- `start-all.sh`: starts the local FastAPI service, legacy social upload backend, and console frontend.
- `.agents/rules/*`: shared agent rules.

## Frontend

Primary frontend:

- `apps/highlight-cutter/frontend`
- Stack: Umi Max, React, TypeScript, Ant Design.
- Routes are configured in `apps/highlight-cutter/frontend/.umirc.ts`.
- Main pages:
  - `src/pages/index.tsx`: short-drama clipping workflow.
  - `src/pages/publish/index.tsx`: publish center UI shell.
  - `src/pages/accounts/index.tsx`: platform account UI shell.
- Reusable UI components:
  - `src/components/layout/*`
  - `src/components/dashboard/*`
  - `src/components/common/*`
  - `src/components/trace/*`
- HTTP clients:
  - `src/services/api.ts` for highlight-service APIs.
  - `src/services/upload.ts` for video upload progress.
  - `src/services/publish.ts` for publish-service API placeholders.

Legacy frontend:

- `apps/social-auto-upload/sau_frontend` is a Vue 3 + Vite + Element Plus app from the upstream publish project.
- Do not treat it as the final console UI unless the user explicitly asks. Current console work should happen in `apps/highlight-cutter/frontend`.

## Backends

Highlight backend:

- `apps/highlight-service`
- Stack: FastAPI.
- Main entry: `app/main.py`.
- Important modules:
  - `app/config.py`: paths and environment settings.
  - `app/db.py`: SQLite access helpers.
  - `app/ffmpeg.py`: video probing and cutting.
  - `app/ai_pipeline.py`, `app/ai_clients.py`: AI enrichment.
  - `app/promo_pipeline.py`: promo video generation.

Social upload backend:

- `apps/social-auto-upload`
- Existing upload automation project with CLI/uploader modules and a legacy Flask backend at `sau_backend.py`.
- Its current Flask API runs on port `5409` when started by `start-all.sh`.
- The target architecture is to wrap or replace this with a cleaner `publish-service`; do not deeply rewrite upstream uploader internals without explicit scope.

## Shared Contracts

- Frontend proxies:
  - `/api` -> highlight-service, default `http://127.0.0.1:8765`.
  - `/publish-api` -> publish service target, default `http://127.0.0.1:8770` in Umi config, overridden to `5409` by `start-all.sh` for the legacy backend.
- Highlight API shape is currently inferred from `apps/highlight-service/app/main.py` and frontend clients in `src/services`.
