from typing import Any

from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver

from core.models import AuditModel
from devices.enums import PayloadStatus


class Device(AuditModel):
    devEUI = models.CharField(max_length=255, unique=True, db_index=True)
    status = models.CharField(max_length=16, choices=PayloadStatus.choices, null=True, blank=True)

    def __str__(self):
        return self.devEUI


class Payload(AuditModel):
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="payloads")
    fCnt = models.IntegerField()
    data = models.CharField(max_length=255)
    status = models.CharField(max_length=16, choices=PayloadStatus.choices)
    raw_payload = models.JSONField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["device", "fCnt"], name="unique_device_fcnt"),
        ]

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

    # Can't move to the top: devices.services imports Device/Payload from here (circular).
    from devices import services  # pylint: disable=import-outside-toplevel,cyclic-import

    services.DeviceStatusSync(instance).apply()
