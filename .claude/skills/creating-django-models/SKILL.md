---
name: creating-django-models
description: Use when adding a new Django model, model field, choices/status enum, or signal handler in this project — e.g. "add a model for X", "add a status field", "create an enum for Y", "add a factory for this model", "add a signal for Z". Documents the established model conventions (AuditModel base, explicit primary key, TextChoices enums, spec-literal field naming, admin registration, factories, where signal handlers live) so new models match the existing ones.
---

# Creating a new model in this project

## Base class

Inherit `core.models.AuditModel`, not bare `django.db.models.Model`:

```python
class Device(AuditModel):
    devEUI = models.CharField(max_length=255, unique=True, db_index=True)
    status = models.CharField(max_length=16, choices=PayloadStatus.choices, null=True, blank=True)

    def __str__(self):
        return self.devEUI
```

`AuditModel` (`core/models.py`) provides:

- `id = models.BigAutoField(primary_key=True)` — kept **explicit** on
  purpose, not left to Django's implicit default. Without it, Pyright (via
  `django-types`, which doesn't rely on a mypy plugin) can't see that a
  model has an `id` at all, and every `.id` access anywhere gets flagged.
  Making it explicit is a no-op at the database level (confirmed via
  `manage.py sqlmigrate` when this was introduced) — it's purely for the
  type checker.
- `audit_created_at` (`auto_now_add=True`), `audit_modified_at`
  (`auto_now=True`).

Primary keys are plain integers (`BigAutoField`), not UUIDs — a deliberate
project decision, not a default left unexamined.

## Choices / status fields

`django.db.models.TextChoices`, defined in the app's `enums.py`:

```python
class PayloadStatus(models.TextChoices):
    PASSING = "passing", "Passing"
    FAILING = "failing", "Failing"
```

Shared/cross-app enums (currently just `ErrorCode`) live in `core/` instead
— see the `creating-endpoint-views` skill. Never a plain `CharField` with
no `choices=` for a fixed set of values, and never `IntegerChoices` unless
the value is genuinely numeric/ordered.

## Field naming

When an external contract/spec mandates a field name that isn't
snake_case (`fCnt`, `devEUI`), use it **literally** — don't rename for
"Pythonic" style; the literal name is the point. Add recurring
spec-mandated names to `[tool.pylint.basic] good-names` in `pyproject.toml`
(already includes `fCnt`, `devEUI`) instead of a per-line
`# pylint: disable=invalid-name` — only add a fresh per-line disable for a
genuinely one-off name that won't recur elsewhere.

## Constraints

Prefer explicit `class Meta: constraints = [models.UniqueConstraint(...)]`
over `unique_together` for anything beyond a single-field `unique=True`:

```python
class Meta:
    constraints = [
        models.UniqueConstraint(fields=["device", "fCnt"], name="unique_device_fcnt"),
    ]
```

## `__str__`

Always implement it, returning something human-identifying — not the
default `f"{class_name} object ({pk})"`. See `Device.__str__` (returns
`devEUI`) and `Payload.__str__` (returns `f"{self.device.devEUI} #{self.fCnt}"`).

## Signals

**A signal handler lives in the same file as the model it's about,
immediately after that model's class definition — never in a separate
`signals.py`.** "About" means: the signal's `sender`/`instance` is an
instance of that model. There is no separate signals file anywhere in this
project; this replaced one that used to exist.

```python
class Payload(AuditModel):
    ...

    def __str__(self):
        return f"{self.device.devEUI} #{self.fCnt}"


@receiver(post_save, sender=Payload)
def sync_device_latest_status(  # pylint: disable=unused-argument
    sender: type[Payload], instance: Payload, created: bool, **kwargs: Any
) -> None:
    """Push a newly-created Payload's status onto its owning Device.

    The services import is deferred to inside the function body (not at
    module level) because devices.services imports Device/Payload from this
    module — a module-level import here would be circular. By the time this
    receiver actually runs, both modules are already fully loaded.
    """

    if not created:
        return

    from devices import services  # pylint: disable=import-outside-toplevel,cyclic-import

    services.DeviceStatusSync(instance).apply()
```

Two things this pattern requires that are easy to get wrong:

- **The first parameter must be named `sender`, exactly.** Django's
  dispatcher calls every receiver with `sender=...` passed as a *keyword*
  argument. Renaming that parameter — even to `_` to satisfy an
  unused-argument lint rule — breaks the call at runtime with a
  `TypeError`, because the keyword can't bind to a differently-named
  parameter. Use `# pylint: disable=unused-argument` instead.
- **If the receiver needs to call into `<app>/services.py`, that import
  must be deferred inside the function body**, not placed at module level.
  `services.py` imports the model(s) from this same `models.py`; a
  module-level `from <app> import services` in `models.py` would be
  circular. Because signal receivers only run at request-handling time —
  long after every module has finished loading — a local import inside the
  function is always safe, regardless of which module happens to get
  imported first.
- Because `models.py` is always auto-imported by Django during normal app
  loading (unlike a standalone `signals.py`, which needed a deferred import
  in `apps.py`'s `ready()` to get imported at all), an app's `apps.py`
  needs **no** custom `ready()` override for signal registration once its
  signals live in `models.py`.

## Admin

Register every new model in the app's `admin.py`, decorator style:

```python
@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("devEUI", "status", "audit_created_at", "audit_modified_at")
    search_fields = ("devEUI",)
    readonly_fields = ("audit_created_at", "audit_modified_at")
```

`@admin.register(...)`, not `admin.site.register(...)` calls. Keep
`audit_created_at`/`audit_modified_at` in `readonly_fields`. No
third-party admin add-ons (django-object-actions, rangefilter, etc.) —
deliberately not part of this project's stack; see `README.md`'s
"Explicitly not included" list.

## Factories

Every model gets a factory-boy factory in the app's `factories.py`:

```python
from factory.declarations import LazyAttribute, Sequence, SubFactory
from factory.django import DjangoModelFactory

class DeviceFactory(DjangoModelFactory):
    class Meta:
        model = Device

    devEUI = Sequence(lambda n: f"{n:016x}")
    status = PayloadStatus.PASSING
```

Import from `factory.declarations` directly (`Sequence`, `SubFactory`,
`LazyAttribute`) rather than `import factory; factory.Sequence(...)` —
factory-boy's package root re-exports these without an explicit `__all__`,
which Pyright flags as a private import (`reportPrivateImportUsage`).
Importing from the submodule sidesteps that with no ignore comment needed.
Use `SubFactory` for FK relationships, `Sequence`/`LazyAttribute` for
computed or uniqueness-constrained fields.

## Migrations

After any model change:

```
uv run python manage.py makemigrations <app>
uv run python manage.py makemigrations --check --dry-run   # confirm no drift
```

Then actually run it against the docker-compose Postgres before
considering the change done — see `README.md`'s "Running locally" for the
`docker-compose up -d db redis` + env-var invocation pattern this project
uses for local (non-container) `manage.py` commands.

## A known rough edge with the type checker

This project uses `django-types` / `djangorestframework-types`, not
`django-stubs` / `djangorestframework-stubs` — the former declares
Django's dynamic attributes statically (works with plain Pyright), the
latter relies on a mypy plugin Pyright doesn't support. Even so, some
Django-generated attributes still aren't visible — most commonly a
`ForeignKey`'s `<name>_id` shortcut (e.g. `payload.device_id`). If a
genuinely correct, more-efficient access like that gets flagged, don't
rewrite it to something less efficient (e.g. `payload.device.id`, which
forces an extra fetch) just to satisfy the checker — use a narrow
`# pyright: ignore[reportAttributeAccessIssue]` with a one-line
justification instead, the way `DeviceStatusSync.apply()` does.
