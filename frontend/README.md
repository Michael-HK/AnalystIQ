# AnalystIQ Professional WebUI

## Stack

- Vite
- React 18 + TypeScript
- Tailwind CSS 3
- shadcn-style UI primitives

## Local development

1. Start API from `PoC_AgentInvest`:
   - `uvicorn web_api:app --reload --port 8000`
2. Start frontend from `frontend`:
   - `npm install`
   - `npm run dev`

The Vite dev server proxies `/api` to `http://127.0.0.1:8000`.

## Production (Render)

The FastAPI app serves the built frontend from `frontend/dist` on the same domain.
Use `VITE_ANALYSTIQ_API_BASE=/api` during build (already set in `render.yaml`).
