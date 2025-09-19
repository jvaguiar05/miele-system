import uuid

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


def custom_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    correlation_id = str(uuid.uuid4())
    if response is None:
        return Response(
            {
                "error": {
                    "code": "internal_error",
                    "message": "Erro interno inesperado.",
                    "details": {},
                    "correlation_id": correlation_id,
                }
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    # Wrap DRF error
    data = {
        "error": {
            "code": getattr(exc, "default_code", "error"),
            "message": getattr(exc, "detail", "Erro"),
            "details": getattr(response, "data", {}),
            "correlation_id": correlation_id,
        }
    }
    return Response(data, status=response.status_code)
