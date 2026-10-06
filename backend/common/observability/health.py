from django.http import JsonResponse
from django.db import connections
from django.db.utils import DatabaseError


def live(_request):
    return JsonResponse({"status": "live"})


def ready(_request):
    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ready"})
