from django.db import IntegrityError, transaction

from core.tests.utils import BaseAPITestCase
from devices.enums import PayloadStatus
from devices.factories import DeviceFactory, PayloadFactory


class TestDevice(BaseAPITestCase):
    def test_str_returns_dev_eui(self):
        """Device.__str__ should return its devEUI."""

        device = DeviceFactory(devEUI="abcdabcdabcdabcd")
        self.assertEqual(str(device), "abcdabcdabcdabcd")


class TestPayload(BaseAPITestCase):
    def test_duplicate_fcnt_for_same_device_is_rejected_at_db_level(self):
        """A second Payload with the same (device, fCnt) should violate the unique constraint."""

        device = DeviceFactory()
        PayloadFactory(device=device, fCnt=100)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PayloadFactory(device=device, fCnt=100)

    def test_same_fcnt_on_different_devices_is_allowed(self):
        """The uniqueness constraint is scoped per-device, not global."""

        first_device = DeviceFactory()
        second_device = DeviceFactory()
        PayloadFactory(device=first_device, fCnt=100)

        payload = PayloadFactory(device=second_device, fCnt=100, status=PayloadStatus.FAILING)

        self.assertEqual(payload.fCnt, 100)


class TestSyncDeviceLatestStatus(BaseAPITestCase):
    def test_creating_a_payload_updates_the_device_status(self):
        """Saving a new Payload should push its status onto the owning Device."""

        device = DeviceFactory(status=PayloadStatus.PASSING)

        PayloadFactory(device=device, status=PayloadStatus.FAILING)

        device.refresh_from_db()
        self.assertEqual(device.status, PayloadStatus.FAILING)

    def test_resaving_an_existing_payload_does_not_reapply_the_update(self):
        """The signal only acts on creation, so an unrelated later save shouldn't matter."""

        device = DeviceFactory(status=PayloadStatus.PASSING)
        payload = PayloadFactory(device=device, status=PayloadStatus.FAILING)

        device.status = PayloadStatus.PASSING
        device.save()
        payload.save()

        device.refresh_from_db()
        self.assertEqual(device.status, PayloadStatus.PASSING)
