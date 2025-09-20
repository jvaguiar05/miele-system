import uuid
import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler
from django.core.exceptions import ValidationError
from django.db import IntegrityError

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """
    Custom exception handler for DRF that provides structured error responses
    while preserving custom authentication and validation errors.
    """
    correlation_id = str(uuid.uuid4())

    # Handle custom API exceptions first (these are our custom exceptions)
    if hasattr(exc, "status_code") and hasattr(exc, "default_code"):
        return Response(
            {
                "error": {
                    "code": exc.default_code,
                    "message": exc.detail,
                    "details": {},
                    "correlation_id": correlation_id,
                }
            },
            status=exc.status_code,
        )

    # Let DRF handle standard exceptions first
    response = drf_exception_handler(exc, context)

    if response is not None:
        # For authentication/authorization errors, preserve the original structure
        if response.status_code in [401, 403]:
            return response

        # For validation errors (400), preserve the original structure to show custom messages
        if response.status_code == 400:
            return response

        # Wrap other DRF errors in our structure
        data = {
            "error": {
                "code": getattr(exc, "default_code", "validation_error"),
                "message": _get_error_message(exc, response),
                "details": response.data,
                "correlation_id": correlation_id,
            }
        }
        return Response(data, status=response.status_code)

    # Handle specific exceptions that DRF doesn't catch
    if isinstance(exc, ValidationError):
        return Response(
            {
                "error": {
                    "code": "validation_error",
                    "message": "Validation failed.",
                    "details": {
                        "validation_errors": (
                            exc.messages if hasattr(exc, "messages") else str(exc)
                        )
                    },
                    "correlation_id": correlation_id,
                }
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if isinstance(exc, IntegrityError):
        return Response(
            {
                "error": {
                    "code": "integrity_error",
                    "message": "Database integrity constraint violated.",
                    "details": {},
                    "correlation_id": correlation_id,
                }
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Log the unhandled exception
    logger.error(
        f"Unhandled exception: {exc}",
        exc_info=True,
        extra={"correlation_id": correlation_id},
    )

    # Only return 500 for truly unhandled exceptions
    return Response(
        {
            "error": {
                "code": "internal_error",
                "message": "An unexpected error occurred. Please try again later.",
                "details": {},
                "correlation_id": correlation_id,
            }
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def _get_error_message(exc, response):
    """Extract a meaningful error message from the exception or response."""
    if hasattr(exc, "detail"):
        detail = exc.detail
        if isinstance(detail, dict):
            # Get the first error message from a dict
            for key, value in detail.items():
                if isinstance(value, list) and value:
                    return str(value[0])
                return str(value)
        elif isinstance(detail, list) and detail:
            return str(detail[0])
        return str(detail)

    return getattr(exc, "default_detail", "An error occurred.")
