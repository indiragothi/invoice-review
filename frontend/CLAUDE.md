# Frontend guidance

Read the root `CLAUDE.md` first. This file adds frontend conventions.

## Stack

Vite single-page React app, strict TypeScript, Tailwind CSS, native `fetch`, pnpm. Not Next.js: no SSR, server components, file-based routing or Node server.

## Layout

```text
frontend/
├── src/
│   ├── components/          # One small component per file
│   │   └── ui/              # Reusable primitives (Button, Badge, Card, Dialog)
│   ├── lib/                 # api.ts, env.ts, types.ts, pure helpers
│   ├── App.tsx              # Workflow: welcome → upload → processing → review
│   ├── main.tsx
│   └── index.css            # Tailwind + theme tokens
├── index.html
├── vite.config.ts
├── package.json
└── pnpm-lock.yaml
```

## Code style

- Strict TypeScript; `unknown` + narrowing over `any`.
- `useState` / `useReducer` / derived values before any state library.
- All HTTP through the typed client in `src/lib/api.ts` with native `fetch`. No Axios.
- API shapes live in `src/lib/types.ts`; components use application-facing types.
- Tailwind only; no CSS modules or CSS-in-JS.
- Make loading, provider failure, validation issues, review state and destructive actions visible.

## Page overlay

Bounding boxes come from the backend in the pixel space of the rendered page image (`GET /api/documents/{id}/pages/{n}`). Scale them with the displayed image size; do not re-render PDFs in the browser. Clicking a field highlights its box; clicking a box selects its field.

## Configuration

`src/lib/env.ts` is the only place that reads `import.meta.env`. `VITE_API_BASE_URL` is validated at startup. Never put secrets in frontend env files.

## Dependencies

pnpm only. Keep `savePrefix: ""`, `minimumReleaseAge: 10080`, `minimumReleaseAgeStrict: true` in `pnpm-workspace.yaml`. Install with `pnpm install --frozen-lockfile`. Ask before adding anything.

## Verification

```bash
pnpm exec tsc -b --pretty false
pnpm lint
pnpm build
```

Plus a manual browser walkthrough: upload, processing, review, correction, ledger, decision, correction email, export, history, delete.
