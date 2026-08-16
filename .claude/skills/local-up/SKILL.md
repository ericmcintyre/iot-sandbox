---
name: local-up
description: Use when the user's entire message is just "local up" (or unambiguously equivalent, like "bring local up"). One-shot bootstrap for this project on any machine, including one with nothing installed but Docker Desktop, or not even that — brings up the full Docker Compose stack, runs migrations, provisions the admin user, opens and logs into the admin site in a browser tab, and copies a ready-to-run curl command for the payload endpoint to the clipboard with a conflict-free fCnt. Every step is idempotent, safe to run repeatedly, including on a machine that's already fully set up.
---

# local up

A single-command bootstrap. The user should be able to restart their
laptop, open Claude Code in this repo, type exactly `local up`, and have
everything below just happen with no other input — including on a brand
new machine with nothing installed except (ideally) Docker Desktop.

Every step here is idempotent. Don't skip a step because "it was probably
already done" — verify, don't assume, since this needs to work identically
on a fresh machine and on one that's already fully set up.

## 1. Docker Desktop must be running

```
docker info > /dev/null 2>&1 && echo RUNNING || echo NOT_RUNNING
```

- **RUNNING**: continue to step 2.
- **NOT_RUNNING, but `docker` command exists**: Docker Desktop is installed
  but not started. Launch it and wait for the daemon:
  ```
  open -a Docker
  ```
  Then poll (don't just sleep once and hope), bounded so it can't hang
  forever — `timeout` isn't available on macOS by default, so use a
  counted loop, not `until ...; done` with no cap:
  ```
  for i in $(seq 1 30); do docker info > /dev/null 2>&1 && break; sleep 3; done
  docker info > /dev/null 2>&1 && echo READY || echo STILL_NOT_READY
  ```
  If it's still `STILL_NOT_READY` after that (~90s), stop and tell the
  user Docker Desktop seems stuck starting — don't loop forever.
- **`docker` command not found at all**: Docker Desktop isn't installed.
  Best-effort: if Homebrew is available, `brew install --cask docker`, then
  `open -a Docker` and poll as above. But be honest with the user if this
  doesn't fully complete — first-run Docker Desktop setup on macOS can
  require accepting a license / granting privileged-helper permissions
  interactively, which can't be reliably scripted. If it gets stuck there,
  say so clearly and tell the user what manual step is needed, rather than
  silently failing or pretending it worked.

## 2. Bring up the stack (README's "Running locally" § Docker Compose)

```
cd <repo root>
[ -f .env ] || cp .env.example .env
docker-compose up -d --build
```

Then wait for the app to actually be answering requests — don't assume
it's ready the instant the container starts (there's no
`depends_on: condition: service_healthy` here, so `web` can start slightly
before `db`/`redis` are truly ready to accept connections). Same
bounded-loop caveat as step 1 — no `timeout` command, use a counted loop:

```
for i in $(seq 1 30); do
  curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/api/health/ | grep -q 200 && break
  sleep 2
done
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8000/api/health/
```

If the final status isn't `200` after that (~60s), report clearly that the
app never came up rather than proceeding as if it did.

## 3. Migrations + admin user

```
docker-compose exec web python manage.py migrate
docker-compose exec web python manage.py create_admin_user
```

Both are idempotent (see `creating-django-models`/README conventions) — no
need to check state first, just run them.

## 4. Open the admin site, logged in, in a browser tab

Use the Claude in Chrome browser tools (`ToolSearch` for
`mcp__claude-in-chrome__*` first if they're deferred). Steps:

1. Get tab context, then create a new tab and navigate it to
   `http://localhost:8000/admin/`.
2. **Check whether it's already logged in before doing anything else** — a
   session cookie from a previous `local up` run may still be valid, in
   which case Django serves the dashboard directly instead of redirecting
   to `/admin/login/`. Read the page; if it's already the admin index (not
   a login form), you're done with this step.
3. If it *is* the login form, fill it in and submit:
   - username: `AdminUserProvisioner.DEFAULT_ADMIN_USERNAME` (`"iot-admin"`)
   - password: `AdminUserProvisioner.DEFAULT_ADMIN_PASSWORD` (`"ResetMe123!"`)
   - `form_input` works well for both fields; click the "Log in" button to
     submit.
4. Verify the login actually succeeded (look for "WELCOME, IOT-ADMIN" /
   "LOG OUT" in the header), don't just assume the click worked — **but
   check in a separate call after the click, not `get_page_text` in the
   same `browser_batch` immediately following it.** The click triggers a
   POST + redirect that isn't finished yet when the very next action in the
   same batch runs, so an immediate same-batch check can read a stale
   pre-redirect snapshot of the login page (still showing the form) even
   though the login actually succeeded. A `computer` `wait` of a second or
   two, or just a fresh tool call afterward, avoids this. Leave the tab
   open and visible when done — that's the whole point of the step.
5. If login fails (e.g. `create_admin_user` reported the user already
   existed *and* someone changed its password by hand since), say so
   explicitly rather than retrying blindly — this project's
   `create_admin_user` deliberately never resets an existing admin's
   password, so this is a real, if rare, possibility.

## 5. Copy a ready-to-run curl for the payload endpoint, conflict-free

This follows the `give-me-the-curl` skill's procedure (default endpoint,
default spec-example body — reproduce `devEUI`/`data`/`rxInfo`/`txInfo`
exactly as documented there), with one deliberate override: **`fCnt` is
computed, not the literal `100` from the spec**, so the copied command
never immediately hits the `(device, fCnt)` uniqueness conflict that
`give-me-the-curl` warns about when run standalone.

Fetch the token and the next `fCnt` in one shell call:

```
docker-compose exec web python manage.py shell -c "
from core.services import TokenProvisioner
from devices.models import Payload
from django.db.models import Max
token = TokenProvisioner.get_ingest_client_auth_key()
max_fcnt = Payload.objects.aggregate(Max('fCnt'))['fCnt__max']
next_fcnt = (max_fcnt + 1) if max_fcnt is not None else 100
print(f'{token}|{next_fcnt}')
"
```

Split the `token|next_fcnt` output on `|`. Build the curl command exactly
like `give-me-the-curl` does, substituting `next_fcnt` for `fCnt` and
leaving every other field untouched:

```
curl -X POST http://localhost:8000/api/payloads/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Token <token>" \
  -d '{
  "fCnt": <next_fcnt>,
  "devEUI": "abcdabcdabcdabcd",
  "data": "AQ==",
  "rxInfo": [
    {"gatewayID": "1234123412341234", "name": "G1", "time": "2022-07-19T11:00:00", "rssi": -57, "loRaSNR": 10}
  ],
  "txInfo": {"frequency": 86810000, "dr": 5}
}'
```

Copy it to the clipboard with `pbcopy` (write to a temp file, `pbcopy <
file`, clean up the temp file — see `give-me-the-curl`), and show it in the
response too.

Note: since `next_fcnt` is always fresh, the resulting `POST` should
succeed with `201` and a new `Payload` should show up under that `Device`
in the admin (`/admin/devices/payload/`) after a refresh — which is
exactly the round-trip the user is checking for when they paste this curl.

## 6. Report back concisely

One short summary: stack up, migrations applied, admin user ready, browser
tab logged in, curl copied with the `fCnt` it used. Don't re-narrate every
command that was run.
