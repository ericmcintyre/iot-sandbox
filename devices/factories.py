from factory.declarations import LazyAttribute, Sequence, SubFactory
from factory.django import DjangoModelFactory

from devices.enums import PayloadStatus
from devices.models import Device, Payload


class DeviceFactory(DjangoModelFactory):
    class Meta:
        model = Device

    devEUI = Sequence(lambda n: f"{n:016x}")
    status = PayloadStatus.PASSING


class PayloadFactory(DjangoModelFactory):
    class Meta:
        model = Payload

    device = SubFactory(DeviceFactory)
    fCnt = Sequence(lambda n: n)
    data = "01"
    status = PayloadStatus.PASSING
    raw_payload = LazyAttribute(
        lambda o: {"fCnt": o.fCnt, "devEUI": o.device.devEUI, "data": "AQ=="}
    )
