# AGENTS.md

This file is the entrypoint for Codex agents working in `/Users/q/Desktop/work/highlight`.

## Project Context

`highlight` is a local short-drama production and distribution workspace. It currently colocates several independent projects:

- `apps/highlight-service`: FastAPI backend for video upload, scanning, highlight cutting, AI analysis, and promo video generation.
- `apps/highlight-cutter/frontend`: Umi Max + React + Ant Design console UI.
- `apps/social-auto-upload`: existing multi-platform upload project with CLI/uploader code and a legacy Flask backend.

The intended architecture keeps services independent and connects them through HTTP APIs. Do not merge backend services or couple frontend code directly to backend internals without an explicit user request.

## Required Rules

- Read these rule files before non-trivial edits:
  - `.agents/rules/common.md`
  - `.agents/rules/project-structure.md`
  - `.agents/rules/development.md`
  - `.agents/rules/validation.md`
  - `.agents/rules/api-contract.md`
- UI work must use existing project components and the installed component library first.
- For the current console frontend, use Ant Design (`antd`) and existing components under `apps/highlight-cutter/frontend/src/components`.
- If Ant Design or existing local components do not provide a suitable component for a UI need, stop and ask the user for secondary confirmation before creating custom UI primitives or introducing another component library.
- Preserve generated/cache/runtime files. Do not edit or commit `.venv`, `node_modules`, `.umi`, `.umi-production`, `dist`, `__pycache__`, runtime logs, uploaded media, or generated output files.

## Common Commands

Start all local services:

```bash
cd /Users/q/Desktop/work/highlight
./start-all.sh
```

Frontend build check:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-cutter/frontend
pnpm build
```

Highlight backend syntax check:

```bash
cd /Users/q/Desktop/work/highlight/apps/highlight-service
python3 -m py_compile app/*.py
```

See `.agents/rules/validation.md` for scoped validation guidance.
