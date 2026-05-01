# TherapInHand Deployment Guide

## 1. Prepare environment variables

Copy `.env.example` to `.env` for local development.

Required production variables:

- `FLASK_ENV=production`
- `DEBUG=0`
- `FLASK_SECRET_KEY=<long random value>`
- `ADMIN_KEY=<separate long random value>`
- `DATABASE_URL=<postgresql://...>`
- `OPENROUTER_API_KEY=<key if AI fallback is enabled>`
- `USE_OPENROUTER_CHAT=1` if OpenRouter should be active
- `SESSION_COOKIE_SECURE=1`
- `REMEMBER_COOKIE_SECURE=1`
- `TRUSTED_HOSTS=<your deployed host names>`
- `CORS_ORIGINS=<comma-separated allowed origins>`

Optional but recommended:

- `LOG_LEVEL=INFO`
- `OPENROUTER_MAX_RETRIES=2`
- `OPENROUTER_TIMEOUT=45`
- `MAX_CONTENT_LENGTH=1048576`

## 2. Install dependencies

```bash
pip install -r requirements.txt
```

## 3. Local production-style run

```bash
gunicorn --bind 0.0.0.0:5000 --workers 3 --threads 2 --timeout 120 --graceful-timeout 30 wsgi:application
```

## 4. Platform notes

### Render

- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn --bind 0.0.0.0:$PORT --workers 3 --threads 2 --timeout 120 --graceful-timeout 30 wsgi:application`
- Health check path: `/health`
- Use PostgreSQL and set `DATABASE_URL` from the managed database

### Railway

- Start command: `gunicorn --bind 0.0.0.0:$PORT --workers 3 --threads 2 --timeout 120 --graceful-timeout 30 wsgi:application`
- Add a PostgreSQL service and connect its `DATABASE_URL`
- Add all secrets from the production env list above

### Replit

- Run command: `gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 2 --timeout 120 wsgi:application`
- Set secrets through the Replit Secrets UI
- SQLite can work for quick demos, but PostgreSQL is recommended for shared deployments

### Local VPS

- Install Python 3.11 and a virtual environment
- Reverse proxy with Nginx or Caddy to Gunicorn
- Keep `ENABLE_PROXY_FIX=1`
- Set `TRUSTED_HOSTS` to your public domain
- Use PostgreSQL for multi-user production deployments

### Vercel frontend

- This project is primarily a Flask server-rendered app, so Vercel is best used only as a separate frontend host if you later split the UI
- Current deployment target for the whole app should remain Render, Railway, Replit, or a VPS

## 5. Post-deploy checks

- Open `/health` and confirm `{"status":"ok"}`
- Register a user
- Log in and out
- Continue as guest
- Create, rename, and delete chats
- Send a chat message and confirm persistence after refresh
- If OpenRouter is enabled, test a prompt that triggers AI fallback
- Review `logs/therapinhand.log` or platform logs for startup or request errors
