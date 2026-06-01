This folder now contains the standalone frontend entry point.

Open `frontend/index.html` directly in a browser. It does not render the report itself. It sends the email and Shopify URL to the backend API, then polls the job status until the worker completes and the email has been sent.

If you later replace this static page with a React/Vite app, keep the same API contract:

- `POST /api/report-requests`
- `GET /api/report-requests/{job_id}`
