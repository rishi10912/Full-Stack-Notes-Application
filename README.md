# Full-Stack Notes App

A full-stack notes application with JWT-authenticated multi-user accounts. Users register, log in, and create/delete notes that are scoped strictly to their own account. Built with a Django REST Framework API and a React (Vite) single-page frontend, backed by a managed Postgres database (Supabase) with an automatic local fallback.

**Stack:** Django REST Framework · Simple JWT · PostgreSQL (Supabase) / SQLite · React 19 · Vite · React Router · Axios

---

## What this project demonstrates

- Designing and consuming a REST API with token-based (JWT) authentication, including access/refresh token rotation
- Per-user data isolation at the query level (users can only ever see or delete their own data — enforced server-side, not just hidden in the UI)
- Migrating an application from a local file database to a managed cloud Postgres instance, including handling the network failure modes that come with talking to infrastructure you don't control
- Working across the full stack: schema design, serializers, API views, routing, and a React UI consuming that API

---

## Architecture

```
┌─────────────────┐        JWT Bearer token         ┌──────────────────────┐
│  React (Vite)    │ ───────────────────────────────▶│  Django REST Framework│
│  localStorage:    │                                  │  /api/user/register/ │
│  access + refresh  │ ◀───────────────────────────────│  /api/token/          │
│  tokens            │        access/refresh tokens     │  /api/token/refresh/  │
└─────────────────┘                                  │  /api/notes/          │
                                                        │  /api/notes/delete/<id>/│
                                                        └──────────┬───────────┘
                                                                   │
                                                      psycopg2 connection probe
                                                          at startup
                                                       ┌───────────┴───────────┐
                                                       │  reachable? → Postgres │
                                                       │  (Supabase, SSL)        │
                                                       │  unreachable? → SQLite │
                                                       │  (backend/db.sqlite3)  │
                                                       └────────────────────────┘
```

- **Backend** (`backend/`) — single Django project (`backend`) with one app (`api`). DRF generic views (`NoteListCreate`, `NoteDelete`, `CreateUserView`) handle CRUD; every queryset is filtered by `request.user` so the database itself enforces data isolation, not just the frontend.
- **Frontend** (`frontend/`) — Vite + React SPA. A shared Axios instance attaches `Authorization: Bearer <token>` to every request via an interceptor; `ProtectedRoute` decodes the JWT client-side to check expiry before rendering protected pages, refreshing the access token if it's stale.
- **Database** — Postgres (Supabase) by default, with a connection-tested automatic fallback to local SQLite if Supabase is unreachable (see below).

---

## Setup

### Backend
```bash
source env/bin/activate          # create with: python -m venv env
cd backend
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver       # http://localhost:8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev                      # http://localhost:5173
```

Environment variables (see `.env.example`): `SECRET_KEY`, `DEBUG`, `DB_NAME`/`DB_USER`/`DB_PWD`/`DB_HOST`/`DB_PORT` for Postgres, and `VITE_API_URL` in `frontend/.env` pointing at the backend.

---

## Engineering deep-dives (STAR)

### 1. Per-user data isolation with JWT authentication

**Situation:** Notes needed to be private per-account — one user should never be able to read, list, or delete another user's notes, even by guessing IDs.

**Task:** Implement stateless authentication suitable for a decoupled SPA + API architecture, and enforce ownership at the data layer rather than relying on the frontend to "hide" other users' notes.

**Action:** Used `rest_framework_simplejwt` for short-lived access tokens (30 min) and longer-lived refresh tokens (1 day), set as the default DRF authentication class so every endpoint requires a valid token unless explicitly opened up (registration uses `AllowAny`). On the backend, `NoteListCreate.get_queryset()` and `NoteDelete.get_queryset()` both filter on `Note.objects.filter(author=request.user)` — so even a maliciously crafted request for someone else's note ID returns a 404, not a permissions error that would leak existence. On the frontend, `ProtectedRoute` decodes the JWT locally with `jwt-decode` to check `exp` before rendering, transparently calling `/api/token/refresh/` to mint a new access token if it's expired, instead of bouncing the user to the login page on every short-lived token expiry.

**Result:** Ownership is enforced at the ORM query level — the security boundary lives in the database query, not in UI logic, so it can't be bypassed by calling the API directly (e.g. via curl/Postman).

### 2. Migrating from local SQLite to managed Postgres (Supabase) with a safety net

**Situation:** The app was built and tested against a local SQLite file. Moving to a real deployment meant connecting to a Supabase-hosted Postgres instance — the first time this database needed to talk to infrastructure outside localhost.

**Task:** Wire up the Postgres connection correctly, and make sure a flaky or misconfigured connection to a remote database couldn't take the whole app down — it needed to degrade gracefully back to local SQLite rather than crash on startup.

**Action:** Found and fixed a config bug where the Django `ENGINE` was already set to `postgresql` but `NAME` was still pointing at a SQLite file path — a copy-paste artifact from converting the settings block. Added `sslmode: require` since Supabase expects TLS on its public endpoint. Then wrote a startup-time connectivity probe: a disposable `psycopg2.connect()` call with a 5-second timeout decides, before Django commits to a `DATABASES` config, whether to use the live Postgres config or fall back to the local SQLite file — with a clear console warning explaining *why* it fell back (e.g. DNS failure, auth failure, timeout), so a failure mode is debuggable instead of silent. Verified this wasn't just theoretical by deliberately pointing `DB_HOST` at an invalid host and confirming the server still started cleanly on SQLite rather than throwing an unhandled exception.

**Result:** The app connects to Supabase by default, but a Supabase outage, network issue, or credential rotation degrades to local-only mode instead of a hard outage — and the failure reason is visible in the logs immediately rather than requiring a debugger session.

### 3. What was the core problem this tech stack solved?

- **JWT over server-side sessions:** the frontend and backend are fully decoupled (separate dev servers, separate deploy targets), so there's no shared session store to lean on. JWT lets the API stay stateless — any backend instance can validate a request without a shared session cache, and the React app can be hosted entirely separately from Django.
- **Django REST Framework over a hand-rolled API:** DRF's generic views (`ListCreateAPIView`, `DestroyAPIView`) collapsed what would otherwise be repetitive CRUD boilerplate (parsing, validation, serialization, response codes) into a few lines, while `get_queryset()` overrides kept the security-critical per-user filtering explicit and in one place per view.
- **Postgres (via Supabase) over staying on SQLite:** SQLite is a single file with no concurrent-write story and no remote access — fine for local development, but it can't be the database for an app with more than one user hitting it at once or a backend that isn't running on the same disk as the database. Supabase gives a managed, networked Postgres instance without standing up and patching a database server by hand.
- **React + Vite over a server-rendered template:** the app is a pure SPA talking to a JSON API, which keeps the frontend deployable as static assets to any CDN/static host, fully independent of the Django deploy.

### 4. What was the hardest part of the build, and how was it solved?

The hardest part was the Postgres migration described in deep-dive #2 — specifically, the failure modes weren't obvious until tested. A misconfigured `NAME` field doesn't throw an error you'd expect from "wrong database name" — Django happily passes whatever's in `NAME` to psycopg2 and lets the driver produce a fairly opaque error. The fix wasn't just correcting the value, but building a system that surfaces *why* a connection failed (auth vs. network vs. timeout) and never lets that failure become a full outage. The approach taken — a cheap, disposable connection probe at startup, separate from Django's actual connection pool — meant the decision of "which database to use" could be made safely without affecting how Django manages connections afterward.

### 5. If rebuilding from scratch tomorrow, what would change architecturally?

- **JWT storage:** tokens currently live in `localStorage`, which is vulnerable to XSS-based token theft. A more secure approach would store the refresh token in an `httpOnly` cookie set by the backend, keeping it inaccessible to any injected JavaScript, with only the short-lived access token held in memory on the frontend.
- **Automatic 401 retry via Axios interceptor:** token refresh currently happens proactively in `ProtectedRoute` on route mount, based on decoding the JWT's `exp` claim client-side. A more robust pattern is a response interceptor that catches `401`s from *any* API call, refreshes the token, and retries the original request transparently — covering the case where a token expires mid-session between route changes, not just on page load.
- **Database connection handling:** the current Postgres/SQLite fallback is a deliberately simple, explicit choice for a single-instance deployment. At scale, this would be replaced with a managed connection pooler (e.g. Supabase's PgBouncer pooler, or PgBouncer directly) and a proper retry/circuit-breaker around transient failures, rather than a one-shot probe at process startup.
- **Test coverage:** `api/tests.py` is currently a scaffold with no tests written. Rebuilding today, API tests (auth flows, ownership enforcement, the 404-not-403 behavior on other users' notes) would be written alongside the views, not after.
- **CORS:** `CORS_ALLOW_ALL_ORIGINS = True` is fine for local development but is the first thing to lock down to an explicit origin allowlist before any real deployment.

---

## License

MIT — see [backend/LICENSE](backend/LICENSE).
