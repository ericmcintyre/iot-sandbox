# iot-sandbox

A Django backend for IoT device payload ingestion, scaffolded with a
specific set of architectural choices (documented below) so new
apps/features can be added on top of a known foundation.

## Stack

| Concern | Choice |
| --- | --- |
| Package manager | [uv](https://docs.astral.sh/uv/) (`pyproject.toml` + `uv.lock`) |
| Python version | 3.12 (pinned in `.python-version`) |
| Database | PostgreSQL |
| Cache | Redis (`django-redis`) |
| Local dev environment | Docker Compose |
| Web server | Nginx (reverse proxy) in front of Gunicorn |
| API framework | Django REST Framework + drf-spectacular (OpenAPI schema/docs) |
| Auth | Django's built-in auth (sessions, `User` model) |
| File storage | Local filesystem |
| Testing | pytest-django runner, django-test-plus `APITestCase` subclasses, factory-boy + Faker |
| Code quality | black + pylint (+ pylint-django) via pre-commit |
| Type checking / IntelliSense | Pyright/Pylance + `django-types` / `djangorestframework-types` |

## Running locally

If you have Claude Code installed, just say **"local up"** and everything
below will be done for you (bringing up Docker, migrating, provisioning
the admin user, logging into the admin in a browser tab, and copying a
ready-to-run curl for the payload endpoint to your clipboard — see the
`local-up` skill). Otherwise, here are the manual steps:

Copy the example env file and adjust as needed:

```
cp .env.example .env
```

### With Docker Compose (recommended)

Runs Postgres, Redis, the Django app (via Gunicorn), and Nginx:

```
docker-compose up --build
docker-compose exec web python manage.py migrate
```

The app is then reachable at `http://localhost:8000/`.

- Health check: `GET /api/health/`
- API docs (Swagger UI): `GET /api/docs/`
- Admin: `/admin/`

Static files (admin CSS/JS, DRF's browsable API styling, Swagger UI's
assets) are collected into `/app/staticfiles` at **image build time**
(`RUN uv run python manage.py collectstatic --noinput` in the `Dockerfile`)
and served by Nginx directly from the shared `static_volume` — Gunicorn
never serves them. If you add a new static asset, rebuild the image
(`docker-compose up --build`) rather than just restarting the container, or
the new file won't be in the volume nginx is serving from.

`nginx/nginx.conf` forwards the Host header as `proxy_set_header Host
$http_host` — **not** nginx's `$host` variable. `$host` silently strips the
port (so a request to `localhost:8000` reaches Django with a Host header of
just `localhost`), which breaks Django's CSRF origin check: it compares the
browser's `Origin: http://localhost:8000` against a "self origin" it
computes from the Host header it received, and `http://localhost` ≠
`http://localhost:8000` gets rejected as a `403 CSRF verification failed`
on every POST (including the admin login form) even though nothing is
actually wrong. If you ever touch this file, keep `$http_host`.

### Without Docker

You still need Postgres and Redis reachable (e.g. `docker-compose up -d db
redis`), then:

```
uv sync --extra dev
uv run python manage.py migrate
uv run python manage.py runserver
```

### Admin user

`python manage.py create_admin_user` gets-or-creates a Django admin
(superuser) account via `core.services.AdminUserProvisioner`, for logging
into `/admin/`:

```
uv run python manage.py create_admin_user
uv run python manage.py create_admin_user --username someone-else
```

`--username` is optional; if omitted, it defaults to
`AdminUserProvisioner.DEFAULT_ADMIN_USERNAME` (`"iot-admin"`). A newly
created user's password is always
`AdminUserProvisioner.DEFAULT_ADMIN_PASSWORD` (`"ResetMe123!"`) — this is a
fixed bootstrapping password, not something generated per-user, and there's
a `TODO` in `core/services.py` to replace it with a real password-reset
flow. The command is safe to re-run: an admin that already exists is left
completely untouched (password and staff/superuser flags included), it's
only set at creation time.

## Project layout

```
config/         Django project package (settings, urls, wsgi/asgi)
api/            DRF app — health check + OpenAPI schema/docs routes
core/           Shared base model (AuditModel) + the structured API error pattern (errors.py, exceptions.py)
devices/        IoT payload ingestion — Device/Payload models, service layer, endpoint
nginx/          Nginx config used by docker-compose
Dockerfile      Image for the `web` service (gunicorn)
docker-compose.yml
gunicorn.conf.py
pyproject.toml  Dependencies + tool config (black, pylint, pytest)
```

## IoT payload ingestion

`POST /api/payloads/` accepts an inbound device payload (`fCnt`, `devEUI`,
base64 `data`, plus passthrough fields like `rxInfo`/`txInfo`), decodes it,
and records it. Token-authenticated — provision the shared client token
with:

```
uv run python manage.py shell -c "
from core.services import TokenProvisioner
print(TokenProvisioner.get_ingest_client_auth_key())
"
```

Full request/response shape, behavior, and the service-layer architecture
behind this endpoint: see `CLAUDE.md`.

## Tests

```
uv run pytest
```

Conventions live in the `writing-unit-tests` skill / `CLAUDE.md`, not here.

## Code quality

```
uv run black .
uv run pylint api config core devices
```

Both are wired into `.pre-commit-config.yaml`:

```
uv run pre-commit install
```

Static type checking is also part of the toolchain — run `npx pyright` to
check the project the same way Pylance does.

## Errors

Every error a view explicitly raises comes back as
`{"error": "<code>", "message": "<human text>"}`. Full pattern (`ErrorCode`,
the `APIError` hierarchy, and its intentional scope/limits): see
`CLAUDE.md`.
