# Validation Rules

## Whole Project

Start all services:

```bash
cd /Users/q/Desktop/work/highlight
./start-all.sh
```

Expected ports from `README.md` and `start-all.sh`:

- Console web: `http://127.0.0.1:8001`
- Highlight API: `http://127.0.0.1:8765`
- Social upload API: `http://127.0.0.1:5409`

If startup fails, inspect:

- `logs/highlight-service.log`
- `logs/social-auto-upload.log`
- `logs/highlight-console.log`

## Frontend

For changes under `apps/highlight-cutter/frontend`:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-cutter/frontend
pnpm build
```

Use browser verification when practical for UI changes. Check:

- desktop and mobile layout behavior
- no text overflow or overlap
- Ant Design controls are used correctly
- loading, empty, success, warning, and error states remain understandable
- `/`, `/publish`, and `/accounts` still route correctly when route or layout code changes

## Highlight Backend

For Python changes under `apps/highlight-service/app`:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-service
python3 -m py_compile app/*.py
```

When API behavior changes, also start the service and check affected endpoints, for example:

```bash
curl http://127.0.0.1:8765/
curl http://127.0.0.1:8765/api/health
```

## Social Auto Upload

For CLI/uploader/backend changes under `apps/social-auto-upload`, inspect `pyproject.toml`, `README.md`, and relevant tests first.

Known available tests include files under `apps/social-auto-upload/tests`, but do not assume all tests are safe to run: some uploader flows may require browser sessions, cookies, or real platform access. Prefer targeted tests or import checks unless the user asks for broader validation.

## Reporting

Always report:

- exact commands run
- pass/fail result
- any command skipped and why
- residual risks, especially browser automation, real platform upload, account cookies, or model/API key behavior
