from core.errors import ErrorCode
from core.exceptions import (
    APIError,
    ConflictAPIError,
    NotFoundAPIError,
    PermissionDeniedAPIError,
    ValidationFailedAPIError,
)
from core.tests.utils import BaseAPITestCase


class TestAPIError(BaseAPITestCase):
    def test_defaults_to_500(self):
        """The base APIError defaults to a 500 status when no subclass overrides it."""

        exc = APIError(code=ErrorCode.INTERNAL_ERROR, message="boom")

        self.assertEqual(exc.status_code, 500)

    def test_detail_matches_the_standard_envelope_shape(self):
        """detail should be exactly {"error": <code>, "message": <text>}, nothing else."""

        exc = APIError(code=ErrorCode.INTERNAL_ERROR, message="boom")

        self.assertEqual(exc.detail, {"error": ErrorCode.INTERNAL_ERROR, "message": "boom"})


class TestAPIErrorSubclassStatusCodes(BaseAPITestCase):
    def test_not_found_api_error_is_404(self):
        self.assertEqual(
            NotFoundAPIError(code=ErrorCode.INTERNAL_ERROR, message="x").status_code, 404
        )

    def test_conflict_api_error_is_409(self):
        self.assertEqual(
            ConflictAPIError(code=ErrorCode.DUPLICATE_PAYLOAD, message="x").status_code, 409
        )

    def test_validation_failed_api_error_is_400(self):
        self.assertEqual(
            ValidationFailedAPIError(code=ErrorCode.INTERNAL_ERROR, message="x").status_code, 400
        )

    def test_permission_denied_api_error_is_403(self):
        self.assertEqual(
            PermissionDeniedAPIError(code=ErrorCode.INTERNAL_ERROR, message="x").status_code, 403
        )
