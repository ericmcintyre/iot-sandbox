from rest_framework import status
from rest_framework.exceptions import APIException

from core.errors import ErrorCode


class APIError(APIException):
    """Base for every domain-specific API error: {"error": <code>, "message": <text>}.

    Subclassing DRF's own APIException means no custom EXCEPTION_HANDLER is
    needed: DRF's default exception handling (already active on every
    APIView) converts any raised APIError into a Response from .detail and
    .status_code automatically. Anything that ISN'T an APIException (a bug,
    a typo, a genuinely unexpected exception) still falls through to
    Django's default 500 untouched, by design.
    """

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

    def __init__(self, code: ErrorCode, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(detail={"error": code, "message": message})


class NotFoundAPIError(APIError):
    status_code = status.HTTP_404_NOT_FOUND


class ConflictAPIError(APIError):
    status_code = status.HTTP_409_CONFLICT


class ValidationFailedAPIError(APIError):
    status_code = status.HTTP_400_BAD_REQUEST


class PermissionDeniedAPIError(APIError):
    status_code = status.HTTP_403_FORBIDDEN
