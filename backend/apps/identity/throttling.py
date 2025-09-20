from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from django.core.cache import cache
import time


class AuthLoginThrottle(AnonRateThrottle):
    """
    Aggressive throttling for login attempts to prevent brute force attacks.
    Allows only 5 attempts per minute for anonymous users.
    """

    scope = "auth_login"
    rate = "5/min"


class AuthRegisterThrottle(AnonRateThrottle):
    """
    Throttling for user registration to prevent spam accounts.
    Allows only 3 registrations per hour per IP.
    """

    scope = "auth_register"
    rate = "3/hour"


class AuthPasswordResetThrottle(AnonRateThrottle):
    """
    Throttling for password reset requests to prevent abuse.
    Allows only 2 attempts per hour per IP.
    """

    scope = "auth_password_reset"
    rate = "2/hour"


class AuthRefreshThrottle(UserRateThrottle):
    """
    Throttling for token refresh to prevent abuse.
    Allows 30 refreshes per hour for authenticated users.
    """

    scope = "auth_refresh"
    rate = "30/hour"


class SensitiveActionThrottle(UserRateThrottle):
    """
    Throttling for sensitive actions like email changes, TOTP enrollment.
    Allows only 10 sensitive actions per hour per user.
    """

    scope = "sensitive_action"
    rate = "10/hour"


class AuthPerUserThrottle(UserRateThrottle):
    """
    Per-user throttling for authenticated auth actions.
    Prevents account takeover attempts from compromised accounts.
    """

    scope = "auth_per_user"
    rate = "20/min"

    def get_cache_key(self, request, view):
        if request.user.is_authenticated:
            # Use user ID for authenticated users
            ident = request.user.pk
        else:
            # Fallback to IP for anonymous users
            ident = self.get_ident(request)

        return self.cache_format % {"scope": self.scope, "ident": ident}


class FailedLoginAttemptThrottle(AnonRateThrottle):
    """
    Special throttling that gets more restrictive after failed login attempts.
    Uses cache to track failed attempts and increases restrictions.
    """

    scope = "failed_login"
    base_rate = "5/min"  # Base rate
    restricted_rate = "1/5min"  # After failed attempts

    def __init__(self):
        super().__init__()

    def get_rate(self):
        # Check if this IP has recent failed attempts
        if hasattr(self, "request"):
            cache_key = f"failed_login_count:{self.get_ident(self.request)}"
            failed_count = cache.get(cache_key, 0)

            if failed_count >= 3:
                return self.restricted_rate

        return self.base_rate

    def allow_request(self, request, view):
        self.request = request  # Store request for get_rate method
        return super().allow_request(request, view)
