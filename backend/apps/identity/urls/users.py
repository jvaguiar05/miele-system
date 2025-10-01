from django.urls import path
from ..views import (
    UserProfileView,
    ChangePasswordView,
    UserDeactivateView,
    EmailChangeRequestView,
    MyChangeRequestsView,
)

urlpatterns = [
    path("me/", UserProfileView.as_view(), name="user_profile"),
    path("password/", ChangePasswordView.as_view(), name="change_password"),
    path("deactivate/", UserDeactivateView.as_view(), name="user_deactivate"),
    path(
        "email/change-request/",
        EmailChangeRequestView.as_view(),
        name="email_change_request",
    ),
    path(
        "my-change-requests/",
        MyChangeRequestsView.as_view(),
        name="my_change_requests",
    ),
]
