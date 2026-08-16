from core.tests.utils import BaseAPITestCase
from devices import services
from devices.enums import PayloadStatus
from devices.factories import DeviceFactory, PayloadFactory
from devices.models import Device, Payload


def build_ingestor(fCnt=1, devEUI="abcdabcdabcdabcd", data="AQ==", raw_payload=None):
    return services.PayloadIngestor(
        fCnt=fCnt, devEUI=devEUI, data=data, raw_payload=raw_payload or {}
    )


class TestDecodeDataToHex(BaseAPITestCase):
    def test_decodes_base64_to_hex_string(self):
        """Base64 "AQ==" is byte 0x01, which hex-encodes to "01"."""

        self.assertEqual(services.PayloadIngestor.decode_data_to_hex("AQ=="), "01")


class TestDetermineStatus(BaseAPITestCase):
    def test_hex_value_of_one_is_passing(self):
        """A decoded value of 1 marks the payload passing."""

        self.assertEqual(services.PayloadIngestor.determine_status("01"), PayloadStatus.PASSING)

    def test_hex_value_other_than_one_is_failing(self):
        """Any decoded value other than 1 marks the payload failing."""

        self.assertEqual(services.PayloadIngestor.determine_status("00"), PayloadStatus.FAILING)


class TestPayloadIngestorIngest(BaseAPITestCase):
    def test_creates_device_for_unseen_dev_eui(self):
        """An unrecognized devEUI should auto-create a Device."""

        build_ingestor().ingest()

        self.assertTrue(Device.objects.filter(devEUI="abcdabcdabcdabcd").exists())

    def test_reuses_existing_device_for_known_dev_eui(self):
        """A recognized devEUI should be attached to the existing Device, not a new one."""

        device = DeviceFactory(devEUI="abcdabcdabcdabcd")

        payload = build_ingestor().ingest()

        self.assertEqual(payload.device.id, device.id)
        self.assertEqual(Device.objects.filter(devEUI="abcdabcdabcdabcd").count(), 1)

    def test_stores_raw_payload_verbatim(self):
        """The full raw request body should be stored alongside the parsed fields."""

        raw_payload = {"fCnt": 1, "devEUI": "abcdabcdabcdabcd", "data": "AQ==", "rxInfo": []}

        payload = build_ingestor(raw_payload=raw_payload).ingest()

        self.assertEqual(payload.raw_payload, raw_payload)

    def test_duplicate_fcnt_for_same_device_raises(self):
        """A repeat (device, fCnt) pair should raise DuplicatePayload rather than create a row."""

        device = DeviceFactory(devEUI="abcdabcdabcdabcd")
        PayloadFactory(device=device, fCnt=1)

        with self.assertRaises(services.DuplicatePayload):
            build_ingestor().ingest()

        self.assertEqual(Payload.objects.filter(device=device, fCnt=1).count(), 1)


class TestDeviceStatusSync(BaseAPITestCase):
    def test_apply_sets_device_status_from_payload(self):
        """The device's status should be overwritten with the given payload's status."""

        device = DeviceFactory(status=PayloadStatus.PASSING)
        payload = PayloadFactory(device=device, status=PayloadStatus.FAILING)

        services.DeviceStatusSync(payload).apply()

        device.refresh_from_db()
        self.assertEqual(device.status, PayloadStatus.FAILING)

    def test_apply_advances_audit_modified_at(self):
        """update() bypasses auto_now, so audit_modified_at must be stamped explicitly."""

        device = DeviceFactory(status=PayloadStatus.PASSING)
        original_modified_at = device.audit_modified_at
        payload = PayloadFactory(device=device, status=PayloadStatus.FAILING)

        services.DeviceStatusSync(payload).apply()

        device.refresh_from_db()
        self.assertGreater(device.audit_modified_at, original_modified_at)
