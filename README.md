# Anonymalous Match Bot

Production-ready Aiogram 3.x webhook bot with Redis + MongoDB + Gemini services.

## Railway notes
- Railway injects `PORT` automatically.
- This project maps `PORT` into webhook server bind port via `config.py`.
- Webhook URL resolution order:
  1. `WEBHOOK_BASE_URL`
  2. `RAILWAY_STATIC_URL`
  3. `RAILWAY_PUBLIC_DOMAIN`

## Run locally
```bash
docker compose up --build
```

## Health check
- `GET /healthz`
