# Mobile GitHub + Free Demo Deploy Guide

## Final bot settings

- Max video: 2 minutes
- Max file: 150MB
- Free trial: first 15 seconds
- Pricing: ₹29 up to 60 sec, ₹49 up to 2 min
- Recharge buttons: ₹49, ₹99, ₹199, ₹499, ₹999, ₹2999, ₹4999, ₹9999

## Files to upload to GitHub

Upload these:

- `bot.py`
- `requirements.txt`
- `Dockerfile`
- `.dockerignore`
- `.gitignore`
- `.env.example`
- `README.md`
- `SECURITY_NOTES.md`
- `DEPLOY_MOBILE_GUIDE.md`
- `assets/`
- `downloads/.gitkeep`

Do not upload:

- `.env`
- bot token
- API keys
- database files
- user videos

## GitHub mobile upload

1. Open GitHub in Chrome.
2. Enable Desktop site.
3. Create private repo: `godmode-video-bot`.
4. Open repo.
5. Tap `Add file` -> `Upload files`.
6. Upload project files.
7. Commit to `main`.

## Free demo deploy on Koyeb

1. Open `https://www.koyeb.com`.
2. Sign up with GitHub.
3. Create App/Service.
4. Choose GitHub repository: `godmode-video-bot`.
5. Build method: Dockerfile.
6. Port: `8080`.
7. Add environment variables.
8. Deploy.
9. Copy Koyeb public URL.
10. Open `https://your-app.koyeb.app/health`.

## Environment variables for demo

Set these in Koyeb/hosting dashboard:

```env
BOT_TOKEN=your_botfather_token
ADMIN_USER_ID=your_telegram_user_id
AICREDITS_API_KEY=your_aicredits_key
AICREDITS_BASE_URL=https://aicredits.in/v1
UPIGATEWAY_API_KEY=your_upigateway_api_key
UPIGATEWAY_SECRET=
WEBHOOK_URL=https://your-koyeb-app.koyeb.app
FLASK_PORT=8080
FONT_PATH=/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf
