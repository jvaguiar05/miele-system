from django.http import JsonResponse


def live(_request):
    return JsonResponse({"status": "live"})


def ready(_request):
    # In real app, check DB/Redis/S3 etc.
    return JsonResponse({"status": "ready"})
