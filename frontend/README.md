# Frontend — Taiwan Stock AI Platform

Next.js 15 (App Router) + TypeScript + Tailwind. Dark-themed fintech dashboard.

## Dev

```bash
npm install
npm run dev
```

→ http://localhost:3000

## Environment

`NEXT_PUBLIC_API_BASE_URL` — defaults to `http://localhost:8000`.

## Scripts

- `npm run dev` — dev server
- `npm run build` — production build
- `npm run start` — run production build
- `npm run lint` — eslint
- `npm run type-check` — tsc --noEmit

## Layout

```
app/
  layout.tsx
  page.tsx              # Dashboard
  globals.css
components/
  layout/Topbar.tsx
  dashboard/StatCard.tsx
  dashboard/Top10Table.tsx
lib/
  api.ts                # backend client
  utils.ts
```
