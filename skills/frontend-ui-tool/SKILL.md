---
name: frontend-ui-tool
description: Use when changing or reviewing the Next.js frontend UI, Tailwind layout, chat/interview pages, resume/job/application screens, or frontend API wrappers.
---

# Frontend UI Tool

## Tool Contract
Use this skill for frontend implementation and verification. This skill has no application-data Python script because frontend work is validated through npm, Vitest, typecheck, build, and browser inspection.

## Script Usage
This skill has no application-data Python script. Run frontend commands from `frontend/`:
```powershell
npm test
npm run typecheck
npm run build
```

## Output Contract
Return test/build status, affected pages/components, and any browser-verification notes. Do not describe hidden backend internals in user-facing UI copy.

## Answer Synthesis
Summarize UI behavior and visible user workflows. Keep text action-oriented and avoid exposing Agent reasoning traces.

## Validation
```powershell
cd frontend
npm test
npm run typecheck
npm run build
```
