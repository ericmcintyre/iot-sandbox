import base64
from typing import Any

from django.db import IntegrityError, transaction
from django.utils import timezone

from devices.enums import PayloadStatus
from devices.models import Device, Payload


class DuplicatePayload(Exception):
    pass


class PayloadIngestor:
    def __init__(self, *, fCnt: int, devEUI: str, data: str, raw_payload: dict[str, Any]):
        self.fCnt = fCnt
        self.devEUI = devEUI
        self.data = data
        self.raw_payload = raw_payload

    @staticmethod
    def decode_data_to_hex(data_b64: str) -> str:
        return base64.b64decode(data_b64).hex()

    @staticmethod
    def determine_status(data_hex: str) -> PayloadStatus:
        value = int(data_hex, 16) if data_hex else None
        return PayloadStatus.PASSING if value == 1 else PayloadStatus.FAILING

    def ingest(self) -> Payload:
        data_hex = self.decode_data_to_hex(self.data)
        status = self.determine_status(data_hex)

        device, _ = Device.objects.get_or_create(devEUI=self.devEUI)

        try:
            with transaction.atomic():
                payload = Payload.objects.create(
                    device=device,
                    fCnt=self.fCnt,
                    data=data_hex,
                    status=status,
                    raw_payload=self.raw_payload,
                )
        except IntegrityError as exc:
            raise DuplicatePayload(f"Duplicate fCnt {self.fCnt} for device {self.devEUI}") from exc

        return payload


class DeviceStatusSync:  # pylint: disable=too-few-public-methods
    """Pushes a Payload's status onto its owning Device.

    A single-purpose command object: one operation (apply), on purpose.
    """

    def __init__(self, payload: Payload):
        self.payload = payload

    def apply(self) -> None:
        """Overwrite the device's status with this payload's status.

        Uses payload.device_id instead of payload.device to avoid fetching
        the related Device row just to update it; django-types doesn't
        statically know about this Django-generated FK shortcut, hence the
        pyright ignore below.

        QuerySet.update() bypasses Model.save(), so it never runs
        audit_modified_at's auto_now logic (that only fires in
        Field.pre_save(), which .update() never calls) — it has to be
        stamped explicitly here or the timestamp would silently go stale.
        """

        device_id: int = self.payload.device_id  # pyright: ignore[reportAttributeAccessIssue]
        Device.objects.filter(pk=device_id).update(
            status=self.payload.status, audit_modified_at=timezone.now()
        )
