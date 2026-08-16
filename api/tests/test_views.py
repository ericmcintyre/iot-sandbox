from core.tests.utils import BaseAPITestCase


class TestHealthView(BaseAPITestCase):
    def test_returns_ok(self):
        """The health check should report ok with no authentication required."""

        response = self.get("health")

        self.response_200(response)
        self.assertEqual(response.json(), {"status": "ok"})
