---
name: creating-endpoint-views
description: Use when adding a new DRF endpoint/view, serializer, or service-layer class in this project — e.g. "add an endpoint for X", "create a new API view", "add a service for Y", "how should this view handle errors". Documents the established layering (serializer validates only, create()/update() delegate to a service class, the view raises APIError subclasses) and the structured error-response pattern (ErrorCode, APIError hierarchy) so new endpoints stay consistent with existing ones.
---

# Creating a new endpoint in this project

Four layers, each with one job. Don't blur them — that's the whole point
of this pattern.

```
urls.py  →  View (APIView)  →  Serializer (validate only)  →  Service (do the work)
```

## URLs

Explicit `path()` entries in the app's `urls.py`, included into
`config/urls.py` under the flat, **unversioned** `/api/` prefix:

```python
# devices/urls.py
from django.urls import path
from devices.views import PayloadIngestView

urlpatterns = [
    path("payloads/", PayloadIngestView.as_view(), name="payload-ingest"),
]
```

No DRF routers or `ViewSet`s anywhere in this project, and no `/api/v1/`
version segment — both were deliberate choices, not omissions. Match the
existing style.

## View

`APIView` subclass, thin. Its job: validate, delegate, translate domain
exceptions into `APIError`s, shape the success `Response`.

```python
class PayloadIngestView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        """Validate and ingest an inbound device payload.

        A repeat (device, fCnt) delivery raises ConflictAPIError rather than
        being silently accepted, so every outcome goes through the same
        structured error shape instead of an ad hoc message.
        """

        serializer = IncomingPayloadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            serializer.save(raw_payload=request.data)
        except services.DuplicatePayload as exc:
            raise ConflictAPIError(code=ErrorCode.DUPLICATE_PAYLOAD, message=str(exc)) from exc

        if serializer.instance is None:
            raise APIError(code=ErrorCode.INTERNAL_ERROR, message="...")

        payload: Payload = serializer.instance
        return Response({...}, status=http_status.HTTP_201_CREATED)
```

Rules to follow:

- `authentication_classes = [TokenAuthentication]`,
  `permission_classes = [IsAuthenticated]` unless there's a specific reason
  for something else.
- Type the method signature: `def post(self, request: Request) -> Response:`.
- Give it a docstring when there's a non-obvious behavior to explain (e.g.
  which domain exceptions get translated to which `APIError`) — see the
  project's global docstring rule in `CLAUDE.md`.
- `serializer.is_valid(raise_exception=True)`, then `serializer.save(...)`.
  Pass any extra context the service needs that isn't itself a validated
  field (e.g. the raw request body, for audit storage) as a `save()` kwarg
  — DRF merges kwargs into `validated_data` before `create()`/`update()`
  sees them.
- Catch the service's domain exceptions and re-raise as the matching
  `APIError` subclass (see "The error pattern" below). Don't let a bare
  domain exception escape the view.
- **Never a bare `assert` for anything reachable from a request.** If
  there's a genuine "this should never happen" invariant to defend, raise
  `APIError(code=ErrorCode.INTERNAL_ERROR, message="...")` explicitly
  instead — an `assert` bypasses the entire structured-response system (and
  disappears completely under `python -O`).
- Read the result back off `serializer.instance` after `.save()` — its
  declared type is `Optional`, so narrow it (an explicit `if ... is None:
  raise APIError(...)`, not a bare assert) before using it.

## Serializer

Validates shape only. No business logic, no persistence logic beyond a
one-line delegation to a service.

```python
class IncomingPayloadSerializer(serializers.Serializer):  # pylint: disable=abstract-method
    """Validates the shape of an inbound device payload; persistence is create()'s job.

    update() is intentionally unimplemented: this serializer is only ever
    constructed with data=..., never instance=..., so .save() always
    dispatches to create() and update() is unreachable.
    """

    fCnt = serializers.IntegerField()
    devEUI = serializers.CharField(max_length=255)
    data = serializers.CharField()  # pyright: ignore[reportAssignmentType]

    def validate_data(self, value):
        try:
            base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise serializers.ValidationError("data must be valid base64.") from exc
        return value

    def create(self, validated_data: dict[str, Any]) -> Payload:
        return PayloadIngestor(**validated_data).ingest()
```

Rules:

- Use a plain `serializers.Serializer`, not `ModelSerializer`, whenever the
  external contract's fields don't map 1:1 onto the model (base64 in, hex
  stored; one external field fans out into a lookup-or-create on a related
  model — like `devEUI` above). Reach for `ModelSerializer` only when the
  mapping really is that direct.
- Field-level `validate_<field>()` methods raise DRF's own
  `serializers.ValidationError` — **never** `APIError`/a subclass here.
  `is_valid()`'s per-field error aggregation specifically catches that
  exact type; raising anything else aborts validation of the remaining
  fields instead of collecting every field's errors together.
- `create()`/`update()` contain no business logic — one line, delegating to
  a service class.
- If `update()` is genuinely unreachable (serializer only ever constructed
  with `data=...`), leave it unimplemented. Add
  `# pylint: disable=abstract-method` on the class line and explain why in
  the class docstring — don't write a dead `NotImplementedError` body, and
  don't implement something that will never run just to silence the linter.
- Spec-mandated external field names that aren't snake_case (`fCnt`,
  `devEUI`) are used literally, not renamed. Recurring spec-literal names
  go in `[tool.pylint.basic] good-names` in `pyproject.toml`, not per-line
  `# pylint: disable=invalid-name` comments.

## Service

Lives in `<app>/services.py` as a small **command-object class**, not a
bare function:

```python
class PayloadIngestor:
    def __init__(self, *, fCnt: int, devEUI: str, data: str, raw_payload: dict[str, Any]):
        self.fCnt = fCnt
        self.devEUI = devEUI
        self.data = data
        self.raw_payload = raw_payload

    @staticmethod
    def decode_data_to_hex(data_b64: str) -> str:
        return base64.b64decode(data_b64).hex()

    def ingest(self) -> Payload:
        ...  # references self.fCnt / self.devEUI / etc., not re-passed args
```

Rules:

- Constructor takes the per-call inputs, set once; one primary method
  (`.ingest()`, `.apply()`, whatever verb fits) does the real work,
  referencing `self.x` instead of re-threading the same values through
  multiple helper functions.
- Pure/stateless helper transforms that don't need per-call state are
  `@staticmethod`s on the same class (`decode_data_to_hex`,
  `determine_status`) — this keeps them independently unit-testable
  without constructing a full instance.
- A service with exactly one real public method is fine — that's the
  expected shape for a single-purpose command object, not a design smell.
  If pylint flags `too-few-public-methods`, add
  `# pylint: disable=too-few-public-methods` with a one-line note in the
  class docstring (see `DeviceStatusSync`) rather than inventing a second
  method just to satisfy the linter.
- Services raise **plain Python domain exceptions**
  (`class DuplicatePayload(Exception): pass`) — never `APIError` or any
  DRF-aware exception. This keeps the service layer usable outside an HTTP
  context (a management command, a background job, ...). Translating a
  domain exception into an HTTP-facing `APIError` is the *view's* job, not
  the service's.
- `QuerySet.update()` bypasses `Model.save()`, so `auto_now` fields (like
  `AuditModel`'s `audit_modified_at`) never update automatically through
  it — if a service uses `.update()` on an audited model, stamp
  `audit_modified_at=timezone.now()` explicitly in the same call (see
  `DeviceStatusSync.apply()`).

## The error pattern

`core/errors.py` — every error code lives here, as a `TextChoices` member.
Never raise with an inline free-text string.

```python
class ErrorCode(models.TextChoices):
    DUPLICATE_PAYLOAD = "duplicate_payload", "Duplicate payload"
    INTERNAL_ERROR = "internal_error", "Internal error"
```

Add a new member only when something actually needs to raise it — don't
pre-populate codes for hypothetical future errors.

`core/exceptions.py` — `APIError(code, message)` (default 500) plus a small
hierarchy of subclasses, **every one of which ends in `APIError`**, each
with a preset HTTP status:

| Class | Status |
|---|---|
| `NotFoundAPIError` | 404 |
| `ConflictAPIError` | 409 |
| `ValidationFailedAPIError` | 400 |
| `PermissionDeniedAPIError` | 403 |

Pick the subclass matching the situation instead of overriding
`status_code` at the call site. If none fits, add a new named subclass
(ending in `APIError`) rather than instantiating the base `APIError` with
an ad hoc status — that's exactly the bug this hierarchy exists to prevent
(the same free-text code silently meaning two different HTTP statuses in
two different places).

`APIError` subclasses DRF's own `APIException`, so raising one needs **no
custom wiring** — no `EXCEPTION_HANDLER` setting. DRF's existing default
exception handling (already active on every `APIView`) converts it to a
`Response` from `.detail`/`.status_code` automatically.

Error response body is always exactly:
```json
{"error": "<code>", "message": "<human text>"}
```

**Scope, deliberately:** this only covers errors a view explicitly raises
via `APIError`. DRF's own built-in exceptions (auth failures,
`is_valid(raise_exception=True)`) keep DRF's default response shape unless
a view explicitly catches and re-raises them. There is no global
catch-all — a genuinely unanticipated exception (a real bug, not something
the code deliberately raises) still falls through to Django's default 500,
unstructured, by design. See `README.md`'s Errors section for the full
reasoning if this ever needs revisiting.

Success responses are **not** wrapped in a matching envelope — also
deliberate. Shape a success `Response` however the endpoint needs.

## Before considering an endpoint done

Write tests per `writing-unit-tests` (auth-required, happy path, every
error path with its exact error body). Then `uv run black .`,
`uv run pylint api config core devices`, `npx pyright`, and
`uv run pytest` (with `docker-compose up -d db redis` running).
