# Shopify Agent Discoverability Enrichment App

This project is split into a backend API and a separate frontend. The frontend only collects the email address and Shopify store URL, then calls the API. The backend queues the job, runs the analysis in a worker, and emails the report when it finishes.

## Backend

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

The backend exposes these endpoints:

- `POST /api/report-requests` to queue a report request
- `GET /api/report-requests/{job_id}` to check request status

## Frontend

Open `frontend/index.html` in your browser. It sends JSON requests to `http://localhost:8000` by default. If you run the backend elsewhere, update the `API_BASE` value in the script.

## Environment

The analysis side still supports the existing provider modes:

- `AI_PROVIDER=gemini`
- `AI_PROVIDER=rules`
- `AI_PROVIDER=ollama`
- `AI_PROVIDER=openai`

Email delivery now supports Gmail OAuth2 and still works with legacy SMTP providers:


For Gmail OAuth2, set:

- `GMAIL_OAUTH_CREDENTIALS_FILE`
- `GMAIL_OAUTH_CLIENT_ID`
- `GMAIL_OAUTH_CLIENT_SECRET`
- `GMAIL_OAUTH_REFRESH_TOKEN`
- `GMAIL_FROM_EMAIL`
- `GMAIL_SMTP_HOST`
- `GMAIL_SMTP_PORT`
- `GMAIL_SMTP_USE_TLS`

You can point `GMAIL_OAUTH_CREDENTIALS_FILE` at the OAuth client JSON downloaded from Google Cloud, then add the refresh token from your consent flow. If you prefer to provide the values directly, set the `GMAIL_OAUTH_CLIENT_ID`, `GMAIL_OAUTH_CLIENT_SECRET`, and `GMAIL_OAUTH_REFRESH_TOKEN` environment variables.

```bash
GMAIL_OAUTH_CREDENTIALS_FILE=/path/to/credentials.json
GMAIL_OAUTH_REFRESH_TOKEN=your-refresh-token
GMAIL_FROM_EMAIL=youraddress@gmail.com
GMAIL_SMTP_HOST=smtp.gmail.com
GMAIL_SMTP_PORT=587
GMAIL_SMTP_USE_TLS=true
```

The Gmail sender uses SMTP with XOAUTH2 under the hood, so no app password is needed.

PDF email delivery also requires WeasyPrint:

```bash
python -m pip install weasyprint
```

Other useful settings remain:

- `SHOPIFY_API_VERSION`
- `MAX_PRODUCTS`
- `AI_MODEL`
- `GEMINI_API_KEY`
- `OPENAI_API_KEY`
