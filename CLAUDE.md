# Working in this repo

A Django/DRF backend. For the stack and how to run it locally, read
`README.md` first — this file is conventions, process, and the domain/error
reference the README only summarizes.

## Skills

Five project skills capture established, non-obvious conventions. Load
the relevant one before doing the matching kind of work rather than
re-deriving the pattern from scratch each time:

- **`writing-unit-tests`** — before writing or modifying any test.
  `BaseAPITestCase`, `self.assert*` (never bare `assert`), factory-boy,
  one-test-per-case, test file/class organization.
- **`creating-endpoint-views`** — before adding a DRF view, serializer, or
  service class. The serializer-validates / service-does-the-work /
  view-translates-errors layering, and the `ErrorCode`/`APIError` pattern.
- **`creating-django-models`** — before adding a model, field, enum, or
  signal handler. `AuditModel` base, `TextChoices`, spec-literal field
  naming, admin registration, factories, migrations, and where signal
  handlers live (with the model they're about, never a separate
  `signals.py`).
- **`give-me-the-curl`** — when the user says "give me the curl" (or asks
  for a curl command for an endpoint). Fetches a real, live token from the
  relevant `core.services` provisioner and copies a ready-to-run command to
  the clipboard — never a placeholder token, and for the payload endpoint,
  the exact body from the original spec by default.
- **`local-up`** — when the user's message is exactly "local up". One-shot
  bootstrap of the whole local environment from nothing: gets Docker
  Desktop running if it isn't, brings up the full Compose stack, runs
  migrations, provisions the admin user, opens and logs into the admin
  site in a browser tab, and copies a conflict-free (auto-incremented
  `fCnt`) curl for the payload endpoint to the clipboard. Every step is
  idempotent, so it's safe to run on a machine that's already set up too.

## IoT payload ingestion

`POST /api/payloads/` accepts an inbound device payload, decodes it, and
records it.

**Auth**: DRF token authentication. Provision the shared `ingest-client`
token via `core.services.TokenProvisioner`, then send it as
`Authorization: Token <key>`:

```
uv run python manage.py shell -c "
from core.services import TokenProvisioner
auth_key = TokenProvisioner.get_ingest_client_auth_key()
print(auth_key)
"
```

`TokenProvisioner` (`core/services.py`) is a small, stateless service (see
the `creating-endpoint-views` skill for the pattern) with three methods:
`get_or_create_token(username)` (a `@staticmethod`) gets-or-creates a user
with that username and its auth token; `ensure_ingest_client_token()` (a
`@classmethod`) calls it with the username `"ingest-client"`;
`get_ingest_client_auth_key()` (a `@classmethod`) calls
`ensure_ingest_client_token()` and returns just the key string, which is
what the shell command above actually uses. All three are idempotent —
calling any of them again returns the same user/token/key rather than
creating a new one.

**Request body**:

```json
{
  "fCnt": 100,
  "devEUI": "abcdabcdabcdabcd",
  "data": "AQ=="
}
```

Extra fields (`rxInfo`, `txInfo`, etc.) are accepted and stored but not
otherwise processed.

**Behavior**:

- `devEUI` identifies the `Device`; an unrecognized `devEUI` auto-creates one
  (`Device.objects.get_or_create`).
- `data` is base64-decoded and converted to a hex string. If the decoded
  value equals `1`, the payload is marked `passing`; otherwise `failing`.
- `Device.status` is kept in sync with the most recent `Payload.status` via a
  `post_save` signal that updates the device row directly
  (`Device.objects.filter(pk=...).update(...)`, not `instance.save()`, so the
  write doesn't re-trigger its own signal).
- `(device, fCnt)` is enforced unique at the database level. A repeat
  `fCnt` for the same device raises a structured `409 Conflict` (see Errors
  below) rather than being silently accepted or creating a second row.
- The full raw request body is stored on `Payload.raw_payload` for
  audit/debugging, separate from the parsed columns.

**Architecture**: business logic lives in `devices/services.py` as small
command-style classes, not the view or serializer:

- `IncomingPayloadSerializer` only validates shape (base64-ness of `data`,
  field types). Its `create()` delegates to `PayloadIngestor`; `update()` is
  intentionally unimplemented since this serializer is only ever constructed
  with `data=...`, never `instance=...`.
- `PayloadIngestor(fCnt=..., devEUI=..., data=..., raw_payload=...)` is a
  command object: all the inputs for one ingestion are set once in the
  constructor, and `.ingest()` runs the whole flow (decode → determine
  status → get-or-create the `Device` → create the `Payload`, raising
  `DuplicatePayload` on a repeat `fCnt`). `decode_data_to_hex()` and
  `determine_status()` are `@staticmethod`s so they stay independently
  testable without constructing a full instance.
- `DeviceStatusSync(payload)` is the same pattern for the signal-triggered
  side effect: `.apply()` pushes `payload.status` onto the owning `Device`.
  The `post_save` receiver that calls it lives in `devices/models.py`
  itself, immediately after the `Payload` class — signal handlers live next
  to the model they're about, not in a separate `signals.py`.
- The view calls `serializer.save(raw_payload=request.data)` (DRF's normal
  idiom) rather than reaching into the service layer directly, and reads the
  result back off `serializer.instance`.

## Errors

Every error a view explicitly raises comes back as
`{"error": "<code>", "message": "<human text>"}`, e.g.:

```json
{"error": "duplicate_payload", "message": "Duplicate fCnt 100 for device abcdabcdabcdabcd"}
```

- `core/errors.py` — `ErrorCode`, a `TextChoices` enum. Every domain error
  gets its own code here; nothing raises a free-text string, so the same
  code can't accidentally end up meaning two different things in two
  different places.
- `core/exceptions.py` — `APIError(code, message)` and a small hierarchy of
  subclasses with preset HTTP statuses: `NotFoundAPIError` (404),
  `ConflictAPIError` (409), `ValidationFailedAPIError` (400),
  `PermissionDeniedAPIError` (403). Pick the subclass that matches the
  situation; the status code isn't something you specify by hand at each
  call site, which is what lets a single free-text error string end up
  meaning 403 in one place and 500 in another.
- `APIError` subclasses DRF's own `APIException`, so raising one requires no
  custom `EXCEPTION_HANDLER` wiring — DRF's default exception handling
  (already active on every `APIView`) turns it into a `Response` from
  `.detail`/`.status_code` automatically.
- **Scope, on purpose**: this only covers errors raised through `APIError`.
  DRF's own built-in exceptions (auth failures, `is_valid(raise_exception=True)`
  validation errors) keep DRF's default response shape
  (`{"detail": "..."}` or `{"field": ["..."]}`) unless a view explicitly
  catches and re-raises them as an `APIError`. A genuinely unanticipated
  exception (a bug, not something the code deliberately raises) still falls
  through to Django's default 500, unstructured — there's no catch-all. If a
  future view has an invariant it wants to defend (in place of an `assert`,
  which would hit that same unstructured fallback if it ever failed), raise
  `APIError`/a subclass explicitly instead, the way `PayloadIngestView.post()`
  does for its "ingestion must have produced a result" check.

## Conventions that apply everywhere (not specific to one skill)

### Docstrings over multi-line comments

If a comment would span more than one line explaining *why* something is
the way it is, it belongs in a docstring on the enclosing class or method,
not a `#` comment block above the code. One-line comments for something
truly local and terse are fine; anything longer gets promoted.

**Exception**: comments that are themselves tool directives —
`# pylint: disable=...`, `# pyright: ignore[...]`, `# noqa: ...` — have to
stay as real inline comments, since the tools parse them from actual
comments, not docstrings. The *surrounding explanation* of why the
suppression is warranted can still live in a docstring; just the terse
directive itself stays pinned to the specific line it governs. See
`devices/services.py`'s `DeviceStatusSync.apply()` for the pattern: the
docstring explains both the `device_id` shortcut and why the
`# pyright: ignore` is there, but the ignore comment itself is still a
same-line comment.

### Blank line after a docstring

Whenever a docstring is immediately followed by code in the same scope,
leave one blank line between the closing `"""` and the next line:

```python
def foo(self):
    """One-line description."""

    do_the_actual_work()
```

This does **not** apply when nothing follows in that scope (the docstring
is the last statement, or is immediately followed only by another
class/function definition that doesn't need separation from it).

### Suppression philosophy (pylint / pyright)

Prefer fixing the real issue over suppressing a finding. When something
truly is an unavoidable framework false positive:

- Default to the **narrowest possible** suppression — a single-line
  `# pylint: disable=...` or `# pyright: ignore[...]` directly on the
  affected line, with a short comment (or docstring, per above) explaining
  why it's a false positive rather than a real bug.
- Only reach for a **project-wide** disable (in `pyproject.toml`'s
  `[tool.pylint."messages control"]`) when the finding is structural and
  would recur on essentially every use of an adopted pattern — e.g.
  `too-many-ancestors` is disabled globally because django-test-plus's
  `TestCase`/`APITestCase` hierarchy trips it on literally every test
  class in the project, not as a matter of convenience.
- **Gotcha**: `black` can reformat a multi-line statement and shift a
  `# pyright: ignore` comment onto a different line than the actual
  flagged expression, silently breaking the suppression (pyright matches
  ignore comments by line number). If a `# pyright: ignore` sits on a line
  black might rewrap, assign the flagged expression to a local variable
  first so the comment has a formatting-stable line to live on — see
  `devices/services.py`'s `device_id: int = self.payload.device_id  #
  pyright: ignore[...]` for the pattern (and its own docstring, which
  explains a case where this bit us).

### Type hints

Annotate new function/method signatures — parameters and return types.
This project is set up for Pyright/Pylance IntelliSense in VS Code
(`django-types`/`djangorestframework-types`, `.vscode/settings.json`
pinned at the project venv with `typeCheckingMode: basic`); untyped code
gets materially worse hover info and autocomplete, not just a missed lint
rule.

### Django signal receivers: the first parameter must be `sender`

Django's dispatcher calls every receiver with `sender=...` passed as a
**keyword** argument (`receiver(signal=self, sender=sender, **named)`).
Renaming that first parameter — even to `_` to satisfy an
unused-argument lint rule — breaks the call at runtime with a `TypeError`,
because Python can't bind a `sender=` keyword to a parameter that isn't
literally named `sender`. Keep the name and silence the linter with
`# pylint: disable=unused-argument` instead. (This has actually broken the
test suite once in this project — see the signal receiver in
`devices/models.py`.)

### Never reference an external "inspiration" codebase in project files

If a convention here was originally adapted from comparing against another
codebase, describe it in this project's own terms in code, comments,
docstrings, commit messages, and docs — never name or leave any trace of
the external codebase anywhere inside this repository.

## Before considering a change done

- `uv run black .`
- `uv run pylint api config core devices`
- `npx pyright` (or rely on the configured VS Code extensions)
- `docker-compose up -d db redis`, then `uv run pytest`
- For any model change: `uv run python manage.py makemigrations --check --dry-run`

All of these are expected to be clean — 0 pylint/pyright issues, all tests
passing — before a change is finished, not just "mostly working."
