from django.urls import include, path
from .views import (
    CustomTokenObtainPairView,
    CustomTokenRefreshView,
    LogoutView,
    RBACView,
    UserProfileView,
    ChangePasswordView,
    AuthThrottleView,
    TOTPEnrollView,
    UserRegistrationView,
    UserDeactivateView,
    EmailChangeRequestView,
    SensibleDataChangeRequestListView,
    MyChangeRequestsView,
    ReviewChangeRequestView,
)

urlpatterns = [
    path("auth/login/", CustomTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("auth/refresh/", CustomTokenRefreshView.as_view(), name="token_refresh"),
    path("auth/logout/", LogoutView.as_view(), name="auth_logout"),
    path("auth/rbac/", RBACView.as_view(), name="rbac_view"),
    path("users/me/", UserProfileView.as_view(), name="user_profile"),
    path("users/password/", ChangePasswordView.as_view(), name="change_password"),
    path("users/deactivate/", UserDeactivateView.as_view(), name="user_deactivate"),
    path(
        "users/email/change-request/",
        EmailChangeRequestView.as_view(),
        name="email_change_request",
    ),
    path(
        "users/my-change-requests/",
        MyChangeRequestsView.as_view(),
        name="my_change_requests",
    ),
    path(
        "admin/change-requests/",
        SensibleDataChangeRequestListView.as_view(),
        name="list_change_requests",
    ),
    path(
        "admin/change-requests/<uuid:request_id>/review/",
        ReviewChangeRequestView.as_view(),
        name="review_change_request",
    ),
    path("auth/throttle-test/", AuthThrottleView.as_view(), name="auth_throttle_test"),
    path("auth/totp/enroll/", TOTPEnrollView.as_view(), name="totp_enroll"),
    path("auth/register/", UserRegistrationView.as_view(), name="user_registration"),
]
