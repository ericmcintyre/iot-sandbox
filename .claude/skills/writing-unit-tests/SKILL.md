---
name: writing-unit-tests
description: Use when writing, adding, or modifying unit tests anywhere in this project — e.g. "add a test for X", "write tests for the new endpoint", "test this service method". Documents the project's established testing conventions (BaseAPITestCase, self.assert* over bare assert, factory-boy, one-test-per-case, docstrings) so every new test matches the existing suite instead of introducing a different style.
---

# Writing unit tests in this project

This project deliberately does **not** use plain pytest-style functions with
`@pytest.mark.django_db`/a `db` fixture, even though pytest-django is the
test runner. Every test is class-based. Follow the pattern below exactly —
it was chosen on purpose, not left over from scaffolding.

## File layout

One `tests/` package per app, split by the module under test — never a flat
`tests.py`:

```
devices/tests/
├── __init__.py
├── test_models.py     # Device, Payload — __str__, constraints
├── test_services.py   # PayloadIngestor, DeviceStatusSync
├── test_signals.py    # the post_save receiver wiring
└── test_views.py       # PayloadIngestView, HTTP-level behavior
```

When adding a new source module (a new service, a new view, a new model),
add a matching `test_<module>.py`, not a new section in an existing file for
an unrelated module.

## Base class and DB access

Every test class subclasses `core.tests.utils.BaseAPITestCase`:

```python
from core.tests.utils import BaseAPITestCase

class TestSomething(BaseAPITestCase):
    def test_does_the_thing(self):
        """One-line description of the behavior under test."""

        ...
```

`BaseAPITestCase` wraps django-test-plus's `APITestCase` (itself DRF's
`APIClient` under the hood). Because it's a `TestCase` subclass, **database
access is automatic** — every test runs inside its own transaction that
rolls back afterward. Do **not** add `@pytest.mark.django_db` or a `db`
fixture parameter anywhere; there is nothing to opt into.

## Assertions

Always `self.assertEqual` / `self.assertTrue` / `self.assertRaises` / etc.
— never a bare `assert` statement in a test. For HTTP status codes, use
test-plus's response helpers instead of checking `.status_code` by hand:
`self.response_200(...)`, `self.response_201(...)`, `self.response_401(...)`,
`self.response_409(...)`, etc. (There's one per common status code; check
`test_plus.test.BaseTestCase` if you need one that isn't obviously named.)

## Making HTTP requests

Use test-plus's `self.get(url_name, ...)` / `self.post(url_name, data=...,
extra={"format": "json"})` — pass the URL **name** from `path(..., name=...)`,
not a hardcoded path string. `extra={"format": "json"}` is required for POST
bodies; without it DRF's test client defaults to multipart. Capture the
return value when the test needs to inspect the body:

```python
response = self.post(PAYLOAD_URL_NAME, data=build_body(fCnt=100), extra={"format": "json"})

self.response_409(response)
self.assertEqual(response.json()["error"], "duplicate_payload")
```

## Auth in tests

Call `self.authenticate()` — a helper on `BaseAPITestCase` that creates a
user + token and attaches it to `self.client` via `credentials()`. Do
**not** use `force_authenticate`, and do not use test-plus's own
`self.login()` — that's session-based and won't satisfy this project's
`TokenAuthentication`-only endpoints.

## Object creation: always factories

Build test data with the factory-boy factories in each app's
`factories.py` (`DeviceFactory`, `PayloadFactory`, ...) — never
`Model.objects.create(...)` directly in a test unless there's a specific
reason to bypass a factory's defaults, and say why in the test if so.

If a test needs several similarly-shaped inputs, add a small builder
function at the top of the file rather than repeating factory calls inline
— see `build_body()` in `devices/tests/test_views.py` and
`build_ingestor()` in `devices/tests/test_services.py`.

## Naming, organization, docstrings

- `test_<snake_case_description_of_behavior_and_condition>` — names should
  make the scenario obvious without reading the body.
- **One test function per case — never `pytest.mark.parametrize`.** This
  was a deliberate choice: every scenario gets its own named, individually
  runnable, individually greppable test.
- Group related cases into sibling `TestXxx(BaseAPITestCase)` classes
  within the same file rather than one giant class — see how
  `test_services.py` splits `TestDecodeDataToHex` / `TestDetermineStatus` /
  `TestPayloadIngestorIngest` / `TestDeviceStatusSync` for the different
  pieces of `devices/services.py`.
- Every test method gets a one-line docstring stating the behavior under
  test, followed by a **blank line** before the body (see this project's
  global docstring rule in `CLAUDE.md` — it applies here too).

## Mocking (not needed yet, but when it is)

No test in this project currently mocks anything. When one needs to,
prefer `unittest.mock` — `patch.object` over string-path `patch(...)` where
possible — not `pytest-mock`'s `mocker` fixture. This is a deliberate
convention choice, not an oversight.

## Explicitly not used — don't reach for these without a real reason first

- `pytest.mark.parametrize` (see above)
- `freezegun` (no test currently needs time control)
- `pytest-rerunfailures` / `pytest-split` (CI-scale tooling; this project's
  suite doesn't need it yet)

## Testing a new service class

- Test `@staticmethod` pure-transform methods directly on the class, no
  instance needed: `services.PayloadIngestor.decode_data_to_hex("AQ==")`.
- Test the instance-driving method (`.ingest()`, `.apply()`, ...) through a
  builder function if construction repeats across several test cases.
- Cover the side effects that matter beyond the return value — e.g.
  `test_apply_advances_audit_modified_at` in `test_services.py` exists
  specifically because `QuerySet.update()` silently skipping `auto_now`
  fields is exactly the kind of regression a test should catch, not just
  documentation.

## Testing a new view

Cover, at minimum:
- the auth-required rejection (`self.response_401()` with no
  `self.authenticate()` call)
- the happy path — assert both the response body **and** the resulting DB
  state (see `test_valid_payload_creates_device_and_payload`)
- each distinct error path, asserting the exact `{"error": "<code>", ...}`
  body (see `test_duplicate_fcnt_returns_conflict_without_creating_a_second_row`)

## Worked example

```python
from core.tests.utils import BaseAPITestCase
from devices.factories import DeviceFactory, PayloadFactory
from devices.enums import PayloadStatus
from devices import services


class TestDeviceStatusSync(BaseAPITestCase):
    def test_apply_sets_device_status_from_payload(self):
        """The device's status should be overwritten with the given payload's status."""

        device = DeviceFactory(status=PayloadStatus.PASSING)
        payload = PayloadFactory(device=device, status=PayloadStatus.FAILING)

        services.DeviceStatusSync(payload).apply()

        device.refresh_from_db()
        self.assertEqual(device.status, PayloadStatus.FAILING)
```

## Before considering a test done

`docker-compose up -d db redis`, then `uv run pytest`. Also run
`uv run black .` and `uv run pylint api config core devices` — new test
files are linted like everything else in this project.
