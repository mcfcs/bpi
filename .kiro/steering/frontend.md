---
inclusion: fileMatch
fileMatchPattern: ["frontend/**"]
---

# Frontend

- Read `frontend/AGENTS.md` first: Next.js 16 differs from training data; its docs are in
  `frontend/node_modules/next/dist/docs/`.
- Design system in `frontend/app/globals.css`: Archivo + Fragment Mono, light by default, BPI red
  `#9A191E` header band with a gold `#D5B625` rule (gold only on red), slate-blue links and charts.
  No component library, no gradients, no BPI logo.
- The browser calls `/api/*` on its own origin; never hard-code the backend URL.
- Verify in a real browser at 1440 and 390 px, light and dark; `npm run typecheck` and `npm run build`.
