from django.db import models


class PayloadStatus(models.TextChoices):
    PASSING = "passing", "Passing"
    FAILING = "failing", "Failing"
