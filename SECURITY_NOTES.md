# Security Notes - GodMode V3

## Money safety
- Payment webhook credits wallet only from stored order amount, not webhook amount.
- Duplicate webhook protection via order status `PENDING` -> `PAID`.
- Wallet debit uses atomic SQLite update.
- Failed paid jobs refund automatically.

## Production warnings
- Do not upload `.env` to GitHub.
- Keep `/data` persistent because wallet DB is stored there.
- Use `UPIGATEWAY_SECRET` if your gateway supports signed webhooks.
- If gateway has status-check API, add server-side verification before final public launch.
- Use HTTPS `WEBHOOK_URL`.

## Render safety
- One worker by default.
- FFmpeg engine avoids MoviePy-heavy RAM usage.
- Per-job temp folder cleanup.
- Disk-space check before render.
