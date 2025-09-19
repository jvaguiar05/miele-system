import uuid

from django.utils.deprecation import MiddlewareMixin


class CorrelationIdMiddleware(MiddlewareMixin):
    def process_request(self, request):
        request.request_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))

    def process_response(self, request, response):
        rid = getattr(request, "request_id", None)
        if rid:
            response["X-Request-Id"] = rid
        return response
