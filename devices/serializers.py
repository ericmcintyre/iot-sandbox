import base64
import binascii
from typing import Any

from rest_framework import serializers

from devices.models import Payload
from devices.services import PayloadIngestor


class IncomingPayloadSerializer(serializers.Serializer):  # pylint: disable=abstract-method
    """Validates the shape of an inbound device payload; persistence is create()'s job.

    update() is intentionally unimplemented: this serializer is only ever
    constructed with data=..., never instance=..., so .save() always
    dispatches to create() and update() is unreachable.

    The "data" field is the external payload's field name (spec-mandated)
    and shadows BaseSerializer.data at the class-body level; DRF's metaclass
    pops declared fields out of the namespace before the class exists, so
    there's no real runtime collision, only a static-analysis one.
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
