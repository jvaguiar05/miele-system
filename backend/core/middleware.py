import uuid
import json
from django.core.cache import cache
from django.utils.deprecation import MiddlewareMixin


class CorrelationIdMiddleware(MiddlewareMixin):
    def process_request(self, request):
        request.request_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))

    def process_response(self, request, response):
        rid = getattr(request, "request_id", None)
        if rid:
            response["X-Request-Id"] = rid
        return response


class FailedLoginTrackingMiddleware(MiddlewareMixin):
    """
    Middleware to track failed login attempts and enhance throttling.
    Works in conjunction with FailedLoginAttemptThrottle.
    """

    def process_response(self, request, response):
        # Only track POST requests to login endpoint
        if (
            request.method == "POST"
            and request.path.endswith("/auth/login/")
            and hasattr(request, "META")
        ):

            # Check if login failed (status 401, 403, or 400 with auth error)
            if response.status_code in [400, 401, 403]:
                try:
                    # Try to parse response to confirm it's an auth error
                    if hasattr(response, "content"):
                        content = json.loads(response.content.decode("utf-8"))
                        # Common error messages that indicate failed login
                        error_indicators = [
                            "credentials",
                            "password",
                            "username",
                            "authentication",
                            "login",
                            "invalid",
                        ]

                        response_text = str(content).lower()
                        is_auth_error = any(
                            indicator in response_text for indicator in error_indicators
                        )

                        if is_auth_error:
                            self._track_failed_attempt(request)

                except (json.JSONDecodeError, UnicodeDecodeError):
                    # If we can't parse response, assume it might be auth-related
                    # for 401/403 status codes
                    if response.status_code in [401, 403]:
                        self._track_failed_attempt(request)

            # Reset counter on successful login (status 200)
            elif response.status_code == 200:
                self._reset_failed_attempts(request)

        return response

    def _track_failed_attempt(self, request):
        """Track a failed login attempt for the IP address."""
        ip = self._get_client_ip(request)
        cache_key = f"failed_login_count:{ip}"

        # Get current count and increment
        current_count = cache.get(cache_key, 0)
        new_count = current_count + 1

        # Store with escalating timeout (longer lockout for repeat offenders)
        if new_count >= 10:
            timeout = 3600  # 1 hour for 10+ failures
        elif new_count >= 5:
            timeout = 1800  # 30 minutes for 5+ failures
        else:
            timeout = 300  # 5 minutes for < 5 failures

        cache.set(cache_key, new_count, timeout)

        # Also track timestamp of last failure
        cache.set(f"failed_login_last:{ip}", True, timeout)

    def _reset_failed_attempts(self, request):
        """Reset failed login counter on successful login."""
        ip = self._get_client_ip(request)
        cache.delete(f"failed_login_count:{ip}")
        cache.delete(f"failed_login_last:{ip}")

    def _get_client_ip(self, request):
        """Get client IP address, considering proxies."""
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip = x_forwarded_for.split(",")[0].strip()
        else:
            ip = request.META.get("REMOTE_ADDR", "127.0.0.1")
        return ip
