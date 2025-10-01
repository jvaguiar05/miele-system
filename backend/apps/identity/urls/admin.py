from django.urls import path
from ..views import (
    SensibleDataChangeRequestListView,
    ReviewChangeRequestView,
)

urlpatterns = [
    path(
        "change-requests/",
        SensibleDataChangeRequestListView.as_view(),
        name="list_change_requests",
    ),
    path(
        "change-requests/<uuid:request_id>/review/",
        ReviewChangeRequestView.as_view(),
        name="review_change_request",
    ),
]
