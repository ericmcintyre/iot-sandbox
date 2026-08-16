from core.tests.utils import BaseAPITestCase
from devices.factories import DeviceFactory, PayloadFactory
from devices.models import Device, Payload

PAYLOAD_URL_NAME = "payload-ingest"


def build_body(fCnt=100, devEUI="abcdabcdabcdabcd", data="AQ=="):
    return {"fCnt": fCnt, "devEUI": devEUI, "data": data}


class TestPayloadIngestView(BaseAPITestCase):
    def test_requires_authentication(self):
        """An unauthenticated request should be rejected."""

        self.post(PAYLOAD_URL_NAME, data=build_body(), extra={"format": "json"})
        self.response_401()

    def test_valid_payload_creates_device_and_payload(self):
        """A first-time devEUI with data decoding to 1 should create both rows as passing."""

        self.authenticate()

        self.post(PAYLOAD_URL_NAME, data=build_body(), extra={"format": "json"})

        self.response_201()
        payload = Payload.objects.get()
        self.assertEqual(payload.fCnt, 100)
        self.assertEqual(payload.data, "01")
        self.assertEqual(payload.status, "passing")
        self.assertEqual(Device.objects.get(devEUI="abcdabcdabcdabcd").status, "passing")

    def test_failing_data_value_marks_payload_and_device_failing(self):
        """A decoded data value other than 1 should mark the payload/device failing."""

        self.authenticate()

        self.post(PAYLOAD_URL_NAME, data=build_body(data="AA=="), extra={"format": "json"})

        self.response_201()
        self.assertEqual(Payload.objects.get().status, "failing")
        self.assertEqual(Device.objects.get().status, "failing")

    def test_duplicate_fcnt_returns_conflict_without_creating_a_second_row(self):
        """A repeat (device, fCnt) delivery should be rejected as a structured 409, not accepted."""

        self.authenticate()
        device = DeviceFactory(devEUI="abcdabcdabcdabcd")
        PayloadFactory(device=device, fCnt=100)

        response = self.post(PAYLOAD_URL_NAME, data=build_body(fCnt=100), extra={"format": "json"})

        self.response_409(response)
        self.assertEqual(response.json()["error"], "duplicate_payload")
        self.assertEqual(Payload.objects.filter(device=device, fCnt=100).count(), 1)
