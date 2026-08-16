from rest_framework import status as http_status
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.errors import ErrorCode
from core.exceptions import APIError, ConflictAPIError
from devices import services
from devices.models import Payload
from devices.serializers import IncomingPayloadSerializer


class PayloadIngestView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        """Validate and ingest an inbound device payload.

        A repeat (device, fCnt) delivery raises ConflictAPIError rather than
        being silently accepted, so every outcome goes through the same
        structured error shape instead of an ad hoc message.
        """

        serializer = IncomingPayloadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            serializer.save(raw_payload=request.data)
        except services.DuplicatePayload as exc:
            raise ConflictAPIError(code=ErrorCode.DUPLICATE_PAYLOAD, message=str(exc)) from exc

        if serializer.instance is None:
            raise APIError(
                code=ErrorCode.INTERNAL_ERROR,
                message="Payload ingestion did not return a result.",
            )

        payload: Payload = serializer.instance

        return Response(
            {
                "id": payload.id,
                "devEUI": payload.device.devEUI,
                "fCnt": payload.fCnt,
                "data": payload.data,
                "status": payload.status,
            },
            status=http_status.HTTP_201_CREATED,
        )
