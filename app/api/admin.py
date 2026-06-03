# app/api/admin.py
from __future__ import annotations

import os
import hmac
from datetime import datetime
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from itsdangerous import URLSafeSerializer, BadSignature

from app.core.database import is_db_available
from app.services.job_repository import job_repo

admin_router = APIRouter()

ADMIN_EMAIL    = os.getenv("ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
ADMIN_SECRET_KEY = os.getenv("ADMIN_SECRET_KEY", "")
signing_key = ADMIN_SECRET_KEY if ADMIN_SECRET_KEY else "fallback-secret-key"
_serializer = URLSafeSerializer(signing_key)
COOKIE_NAME    = "admin_session"


# ── Session helpers ───────────────────────────────────────────────────────

def _make_cookie() -> str:
    return _serializer.dumps({"auth": True})


def _is_authenticated(request: Request) -> bool:
    cookie = request.cookies.get(COOKIE_NAME)
    if not cookie:
        return False
    try:
        data = _serializer.loads(cookie)
        return data.get("auth") is True
    except BadSignature:
        return False


def _safe_compare(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


# ── HTML helpers ──────────────────────────────────────────────────────────

def _status_badge(status: str) -> str:
    colours = {
        "completed":  "#1a7f4b",
        "failed":     "#b43d31",
        "processing": "#b87524",
        "queued":     "#4a6fa5",
    }
    colour = colours.get(status, "#666")
    return (
        f'<span style="display:inline-block;padding:2px 10px;border-radius:999px;'
        f'background:{colour};color:#fff;font-size:11px;font-weight:700;'
        f'text-transform:uppercase;letter-spacing:.04em">{status}</span>'
    )


def _fmt_dt(value: datetime | str | None) -> str:
    if value is None:
        return "—"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M UTC")
    return str(value)


def _build_table_rows(jobs: list) -> str:
    if not jobs:
        return (
            '<tr><td colspan="8" style="text-align:center;color:#888;padding:28px">'
            "No records found.</td></tr>"
        )
    rows = []
    for job in jobs:
        job_id     = getattr(job, "job_id",    "—")
        email      = getattr(job, "email",     "—")
        store_url  = getattr(job, "store_url", "—")
        status     = getattr(job, "status",    "—")
        error      = getattr(job, "error",     None) or "—"
        created    = _fmt_dt(getattr(job, "created_at", None))
        has_report = "✅" if getattr(job, "report", None) else "❌"

        short_id  = str(job_id)[:8] + "…"
        short_url = str(store_url)[:40] + ("…" if len(str(store_url)) > 40 else "")
        short_err = (
            str(error)[:60] + ("…" if len(str(error)) > 60 else "")
            if error != "—" else "—"
        )

        rows.append(f"""
        <tr>
          <td title="{job_id}"
              style="font-family:monospace;font-size:12px;color:#555">{short_id}</td>
          <td>{email}</td>
          <td title="{store_url}">
            <a href="{store_url}" target="_blank" style="color:#17695b">{short_url}</a>
          </td>
          <td>{_status_badge(status)}</td>
          <td style="text-align:center">{has_report}</td>
          <td style="font-size:12px;color:#666">{created}</td>
          <td title="{error}"
              style="font-size:11px;color:#c0392b;max-width:160px;
                     overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
            {short_err}
          </td>
        </tr>""")
    return "\n".join(rows)


def _build_summary(jobs: list) -> dict:
    return {
        "total":      len(jobs),
        "completed":  sum(1 for j in jobs if getattr(j, "status", "") == "completed"),
        "failed":     sum(1 for j in jobs if getattr(j, "status", "") == "failed"),
        "processing": sum(
            1 for j in jobs if getattr(j, "status", "") in ("processing", "queued")
        ),
    }


# ── Login page ────────────────────────────────────────────────────────────

def _login_html(error: str = "") -> str:
    error_block = (
        f'<div class="error">{error}</div>' if error else ""
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Admin Login</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:Arial,Helvetica,sans-serif;background:#f4f4f4;
          display:flex;align-items:center;justify-content:center;min-height:100vh}}
    .card{{background:#fff;border:1px solid #e0ddd6;border-radius:14px;
           padding:40px 36px;width:100%;max-width:400px;
           box-shadow:0 8px 32px rgba(16,24,40,.09)}}
    .logo{{text-align:center;font-size:36px;margin-bottom:18px}}
    h1{{text-align:center;font-size:21px;font-weight:800;
        color:#16302b;margin-bottom:4px}}
    .sub{{text-align:center;font-size:13px;color:#999;margin-bottom:28px}}
    label{{display:block;font-size:13px;font-weight:700;
           margin-bottom:5px;color:#444}}
    input{{width:100%;padding:11px 13px;border:1px solid #ddd;
           border-radius:8px;font-size:14px;margin-bottom:18px;
           outline:none;transition:border .15s}}
    input:focus{{border-color:#17695b;box-shadow:0 0 0 3px rgba(23,105,91,.08)}}
    button{{width:100%;padding:13px;background:#16302b;color:#fff;
            border:0;border-radius:8px;font-size:15px;font-weight:700;
            cursor:pointer;transition:background .15s}}
    button:hover{{background:#17695b}}
    .error{{background:#fff2f2;border:1px solid #f3c2c2;color:#8a2f24;
            border-radius:8px;padding:10px 13px;font-size:13px;
            margin-bottom:18px;text-align:center}}
  </style>
</head>
<body>
  <div class="card">
    <div class="logo">🛠</div>
    <h1>Admin Panel</h1>
    <p class="sub">Shopify Enrichment App</p>
    {error_block}
    <form method="post" action="/admin/login">
      <label for="email">Email</label>
      <input id="email" name="email" type="email"
             placeholder="admin@yourdomain.com"
             required autocomplete="email">
      <label for="password">Password</label>
      <input id="password" name="password" type="password"
             placeholder="••••••••"
             required autocomplete="current-password">
      <button type="submit">Sign in</button>
    </form>
  </div>
</body>
</html>"""


# ── Routes ────────────────────────────────────────────────────────────────

@admin_router.get("/admin/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    if _is_authenticated(request):
        return RedirectResponse(url="/admin", status_code=302)
    return HTMLResponse(_login_html())


@admin_router.post("/admin/login")
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
) -> RedirectResponse | HTMLResponse:
    email_ok    = _safe_compare(email.strip().lower(), ADMIN_EMAIL.strip().lower())
    password_ok = _safe_compare(password, ADMIN_PASSWORD)

    if not (email_ok and password_ok):
        return HTMLResponse(_login_html(error="Incorrect email or password."), status_code=401)
    response = RedirectResponse(url="/admin", status_code=302)
    response.set_cookie(
        key=COOKIE_NAME,
        value=_make_cookie(),
        httponly=True,   
        samesite="lax",   
        secure=False,     
    )
    return response


@admin_router.get("/admin/logout")
def logout() -> RedirectResponse:
    response = RedirectResponse(url="/admin/login", status_code=302)
    response.delete_cookie(COOKIE_NAME)
    return response


@admin_router.get("/admin", response_class=HTMLResponse)
def admin_panel(request: Request) -> HTMLResponse:
    if not _is_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=302)

    if is_db_available():
        jobs = job_repo.recent(limit=200)
    else:
        from app.services.jobs import job_queue
        with job_queue._lock:
            jobs = list(job_queue._jobs.values())
        jobs.sort(key=lambda j: getattr(j, "created_at", ""), reverse=True)

    stats = _build_summary(jobs)
    rows  = _build_table_rows(jobs)
    db_status = (
        '<span style="color:#1a7f4b">● Connected</span>'
        if is_db_available()
        else '<span style="color:#b87524">● In-memory only</span>'
    )

    return HTMLResponse(f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Admin – Shopify Enrichment</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:Arial,Helvetica,sans-serif;background:#f4f4f4;
          color:#111;font-size:14px}}
    .topbar{{background:#16302b;color:#f0ebe0;padding:14px 28px;
             display:flex;align-items:center;justify-content:space-between;gap:12px}}
    .topbar h1{{font-size:17px;font-weight:700}}
    .topbar-right{{display:flex;align-items:center;gap:16px;font-size:12px;
                   flex-shrink:0}}
    .logout{{color:#f0ebe0;opacity:.75;text-decoration:none;
             border:1px solid rgba(240,235,224,.3);padding:5px 12px;
             border-radius:6px;transition:opacity .15s}}
    .logout:hover{{opacity:1}}
    .body{{padding:24px 28px}}
    .stats{{display:grid;grid-template-columns:repeat(4,1fr);
            gap:14px;margin-bottom:22px}}
    .card{{background:#fff;border:1px solid #e0ddd6;
           border-radius:10px;padding:16px 18px}}
    .card .num{{font-size:28px;font-weight:800;line-height:1;margin:6px 0 4px}}
    .card .lbl{{font-size:11px;text-transform:uppercase;
                letter-spacing:.06em;color:#888;font-weight:700}}
    .card.completed .num{{color:#1a7f4b}}
    .card.failed    .num{{color:#b43d31}}
    .card.processing .num{{color:#b87524}}
    .toolbar{{display:flex;align-items:center;gap:12px;
              margin-bottom:14px;flex-wrap:wrap}}
    .toolbar input{{padding:8px 12px;border:1px solid #ddd;border-radius:8px;
                    font-size:13px;width:240px;outline:none}}
    .toolbar input:focus{{border-color:#17695b}}
    .toolbar select{{padding:8px 12px;border:1px solid #ddd;
                     border-radius:8px;font-size:13px}}
    .db-badge{{font-size:12px;margin-left:auto}}
    .table-wrap{{overflow-x:auto;background:#fff;
                 border:1px solid #e0ddd6;border-radius:10px}}
    table{{width:100%;border-collapse:collapse}}
    thead th{{background:#f8f6f0;padding:10px 12px;text-align:left;
              font-size:11px;font-weight:800;text-transform:uppercase;
              letter-spacing:.06em;color:#666;border-bottom:1px solid #e0ddd6;
              white-space:nowrap}}
    tbody tr{{border-bottom:1px solid #f0ede6;transition:background .1s}}
    tbody tr:hover{{background:#faf8f4}}
    tbody td{{padding:10px 12px;vertical-align:middle}}
    tbody tr:last-child{{border-bottom:none}}
    .btn{{padding:8px 14px;background:#17695b;color:#fff;border:0;
          border-radius:8px;font-size:13px;font-weight:700;cursor:pointer}}
    .footer{{margin-top:16px;font-size:11px;color:#aaa;text-align:right}}
  </style>
</head>
<body>
  <div class="topbar">
    <h1>🛠 Admin Panel – Shopify Enrichment App</h1>
    <div class="topbar-right">
      <span id="clock"></span>
      <span>Signed in as <strong>{ADMIN_EMAIL}</strong></span>
      <a href="/admin/logout" class="logout">Sign out</a>
    </div>
  </div>

  <div class="body">
    <div class="stats">
      <div class="card">
        <div class="lbl">Total requests</div>
        <div class="num">{stats["total"]}</div>
      </div>
      <div class="card completed">
        <div class="lbl">Completed</div>
        <div class="num">{stats["completed"]}</div>
      </div>
      <div class="card failed">
        <div class="lbl">Failed</div>
        <div class="num">{stats["failed"]}</div>
      </div>
      <div class="card processing">
        <div class="lbl">Queued / Processing</div>
        <div class="num">{stats["processing"]}</div>
      </div>
    </div>

    <div class="toolbar">
      <input type="text" id="search"
             placeholder="Search email or store URL…"
             oninput="filterTable()">
      <select id="status-filter" onchange="filterTable()">
        <option value="">All statuses</option>
        <option value="completed">Completed</option>
        <option value="failed">Failed</option>
        <option value="processing">Processing</option>
        <option value="queued">Queued</option>
      </select>
      <button class="btn" onclick="location.reload()">↻ Refresh</button>
      <span class="db-badge">Database: {db_status}</span>
    </div>

    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Job ID</th><th>Email</th><th>Store URL</th>
            <th>Status</th><th>PDF</th><th>Language</th>
            <th>Created</th><th>Error</th>
          </tr>
        </thead>
        <tbody id="table-body">
          {rows}
        </tbody>
      </table>
    </div>
    <div class="footer">
      Showing up to 200 most recent · {stats["total"]} total
    </div>
  </div>

  <script>
    function tick(){{
      document.getElementById('clock').textContent = new Date().toUTCString();
    }}
    tick(); setInterval(tick,1000);

    function filterTable(){{
      const q      = document.getElementById('search').value.toLowerCase();
      const status = document.getElementById('status-filter').value.toLowerCase();
      document.querySelectorAll('#table-body tr').forEach(row => {{
        const text  = row.textContent.toLowerCase();
        const badge = row.querySelector('span') ?
                      row.querySelector('span').textContent.toLowerCase() : '';
        const matchQ = !q      || text.includes(q);
        const matchS = !status || badge.includes(status);
        row.style.display = (matchQ && matchS) ? '' : 'none';
      }});
    }}
  </script>
</body>
</html>""")