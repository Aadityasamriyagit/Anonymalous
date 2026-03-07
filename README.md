# Anonymalous Match Bot

Production-ready Aiogram 3.x webhook bot with Redis + MongoDB + Gemini services.

## Minimal environment variables
Only **4** are required:
- `BOT_TOKEN`
- `MONGO_URI`
- `REDIS_URL`
- `GEMINI_API_KEY`

Webhook URL must also be discoverable through one of:
- `WEBHOOK_BASE_URL` (recommended)
- `RAILWAY_STATIC_URL` (Railway)
- `RAILWAY_PUBLIC_DOMAIN` (Railway)

Notes:
- `PORT` is auto-injected by Railway and automatically used by the app.
- Webhook secret is auto-derived from `BOT_TOKEN` (no extra env var needed).

## Run locally
```bash
docker compose up --build
```

## Health check
- `GET /healthz`
