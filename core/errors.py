from django.db import models


class ErrorCode(models.TextChoices):
    DUPLICATE_PAYLOAD = "duplicate_payload", "Duplicate payload"
    INTERNAL_ERROR = "internal_error", "Internal error"
