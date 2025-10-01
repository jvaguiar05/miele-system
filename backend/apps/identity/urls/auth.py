from django.urls import path
from ..views import (
    CustomTokenObtainPairView,
    CustomTokenRefreshView,
    LogoutView,
    RBACView,
    AuthThrottleView,
    TOTPEnrollView,
    UserRegistrationView,
)

urlpatterns = [
    path("login/", CustomTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("refresh/", CustomTokenRefreshView.as_view(), name="token_refresh"),
    path("logout/", LogoutView.as_view(), name="auth_logout"),
    path("rbac/", RBACView.as_view(), name="rbac_view"),
    path("throttle-test/", AuthThrottleView.as_view(), name="auth_throttle_test"),
    path("totp/enroll/", TOTPEnrollView.as_view(), name="totp_enroll"),
    path("register/", UserRegistrationView.as_view(), name="user_registration"),
]
