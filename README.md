# TaskFlow API

[![CI](https://github.com/Joaovictoreth1/taskflow-backend-api/actions/workflows/ci.yml/badge.svg)](https://github.com/Joaovictoreth1/taskflow-backend-api/actions/workflows/ci.yml)

A FastAPI service for private projects, task assignments, labels, comments, analytics, and CSV export. Python 3.11–3.12, Pydantic, SQLAlchemy, Alembic, PostgreSQL, and Redis; SQLite is supported for local development.

## Run locally

```sh
python -m venv .venv
. .venv/bin/activate
make install
cp .env.example .env
python -c 'import secrets; print(secrets.token_hex(32))'
# Set SECRET_KEY in .env to the generated value.
make migrate
make run
```

The local API is at `http://127.0.0.1:8000`; OpenAPI docs are at `/docs`. To create a sample project, run `python seed.py` with a development-only `SEED_PASSWORD` supplied through the environment. The atomic seed creates owner and collaborator accounts and grants the demo owner access to the separate student directory.

## API and permissions

Register at `POST /auth/register` with `username`, `email`, and `password`. Use JSON at `POST /auth/login`, or OAuth2 form fields at `POST /auth/token` (used by Swagger's Authorize dialog). Send the returned `access_token` as `Authorization: Bearer <token>`.

```sh
curl http://127.0.0.1:8000/projects \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"name":"Launch checklist"}'
curl 'http://127.0.0.1:8000/tasks?status=todo&priority=high&page=1&size=25' \
  -H "Authorization: Bearer $TOKEN"
```

| Resource | Contract |
| --- | --- |
| Projects | Only the owner can list, read, change, delete, export, or view project KPIs. Both list routes return project summaries. Project detail includes the first 100 tasks; paginate the full set at `/projects/{id}/tasks` with `skip` and `limit`. |
| Tasks | Only the owner can create, update, assign, delete, or attach labels. An active assignee can read the assigned task, not the project or its other tasks. `/tasks` supports project, assignee, status, priority, tag, and text filters; `/tasks/my-tasks` lists assignments. |
| Comments | Owners and assignees can read and post on visible tasks. An author can delete their own comment; the project owner can moderate any comment on that task. Lists use `skip` and `limit`. |
| Tags | Names are unique per account. Only an owner can attach their own label or delete it. The catalog is paginated; an assignee can see labels attached to their assigned task. |
| Analytics and export | `/analytics/overview` aggregates only projects owned by the caller. Project analytics and CSV are owner-only. CSV exports stream rows and neutralize spreadsheet formulas in text cells. |
| Student directory | Student/profile endpoints require a directory administrator. Self-registration cannot grant the role. |

Missing credentials produce `401`. Requests for objects outside the caller's scope return `404`. Errors use a `detail` field, with field-level validation errors in an array and no submitted credential values. Conflicting writes can return `409`. Password rotation invalidates all previously issued tokens for that account. New passwords must contain at least eight characters and at most 72 UTF-8 bytes.

## Deploy

For a local production-like stack set `SECRET_KEY`, `POSTGRES_PASSWORD`, and `COMPOSE_DATABASE_URL` in `.env` as described below, then run `docker compose up --build --wait`. Compose migrates PostgreSQL with a one-shot container before starting the non-root API. Only the API port binds to localhost. For deployment, run the migration once before releasing API replicas. Use TLS at the reverse proxy, restrict PostgreSQL and Redis to private networks, and configure proxy trust narrowly.

| Variable | Use |
| --- | --- |
| `APP_ENV` | `development` (default), `test`, or `production`; production requires PostgreSQL and Redis. Compose uses production mode. |
| `SECRET_KEY` | Required for the API. Generate from at least 32 random bytes; use the same value across replicas. Never reuse the old sample/default keys. |
| `DATABASE_URL` | Defaults to `sqlite:///./taskflow.db`. PostgreSQL examples use `postgresql+psycopg://user:password@host:5432/db`; percent-encode URL credentials. Compose sets this from `COMPOSE_DATABASE_URL`. |
| `RATE_LIMIT_STORAGE_URI` | `memory://` in development; use `redis://` or `rediss://` in production, shared across replicas. Compose uses a private Redis service. |
| `CORS_ORIGINS` | JSON array of exact UI origins; default `[]` disables cross-origin browser access. No wildcards or cookie credentials. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access-token lifetime, 1–1440 minutes (default 60). |
| `MAX_REQUEST_BODY_BYTES` | Maximum bytes accepted in JSON/form request bodies (default 65536). Set a matching or tighter limit at ingress. |
| `FORWARDED_ALLOW_IPS` | Uvicorn's list of trusted proxy IPs or networks. Do not use `*`; IP-based limits depend on trusted client-IP forwarding. |
| `POSTGRES_PASSWORD`, `COMPOSE_DATABASE_URL`, `API_PORT` | Compose only: database password, matching DSN using host `db`, and localhost API port (default 8000). |

`GET /health` is a process liveness probe. `GET /ready` returns success only when the database is reachable and at the current Alembic revision. Synchronous route handlers use the framework's worker pool, one SQLAlchemy session per request, and database-enforced foreign keys. The policy dependencies select rows by scope before CRUD operations; query code batches tags, computes KPIs in SQL, and streams CSV using bounded row batches.

### Upgrade an existing database

1. Back up the database and rehearse the migration against a restore. Stop writes for the migration. If the database already has an Alembic revision, run `alembic upgrade head`. If it has **no** revision because the old API created tables at startup, first confirm it matches the previous schema (including `task_comments`, `tags`, `task_tags`, and `tasks.assignee_id`), then run `alembic stamp 204f57baebb7` once and upgrade. Do not stamp an empty or partially upgraded database.
2. Replace any old JWT key and checked-in Compose database password used in a deployment. If PostgreSQL already has a volume, rotate the existing database role password separately; changing the Compose initialization variable will not rotate it. Replace the API's DSN and have clients sign in again. Existing bcrypt passwords longer than 72 bytes require an administrator-assisted reset; the API no longer truncates them.
3. Review ownerless legacy projects and assign them only to verified owners with a reviewed database update. Unclaimed projects, their assignments, and unused unowned tags are intentionally inaccessible via the API. Existing labels in owned projects are copied to their respective owners. Grant `users.is_superuser` only to verified directory administrators through an audited database change.
4. Deploy the API and verify `/ready`. For rollback after accepting writes, prefer restoring the backup after planning for those writes: downgrading merges account-specific labels of the same name back into one label.

## Verify

```sh
make check                           # Ruff lint and formatting, strict mypy, tests and dependency audit
TEST_POSTGRES_URL=... make test       # dedicated empty PostgreSQL test database, never a live database
make smoke                           # disposable Compose stack; builds the image and tests the running API
```

CI verifies SQLite on Python 3.11 and PostgreSQL on Python 3.12, with a 90% application coverage gate. Integration tests check migrations, authentication and isolation, conflict recovery, and query budgets. The PostgreSQL job also exercises concurrent label attachment. The Compose smoke test creates an isolated stack with generated credentials and tears it down afterward.
