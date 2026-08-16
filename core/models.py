from django.db import models


class AuditModel(models.Model):
    id = models.BigAutoField(primary_key=True)  # explicit for static type-checkers
    audit_created_at = models.DateTimeField(auto_now_add=True)
    audit_modified_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
