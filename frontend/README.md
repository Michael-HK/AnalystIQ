# AnalystIQ Professional WebUI

## Stack

- Vite
- React 18 + TypeScript
- Tailwind CSS 3
- shadcn-style UI primitives

## Local development

1. Start API:
   - `uvicorn web_api:app --reload --port 8000` from `PoC_AgentInvest`.
2. Start frontend:
   - `npm install`
   - `npm run dev`

Set `VITE_ANALYSTIQ_API_BASE` in `.env.local` if API is not at `http://localhost:8000`.
