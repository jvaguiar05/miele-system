from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .deadline_views import preview, upcoming_report
from .report_views import status_report, deadline_history
from .views import (
    PerDcompViewSet,
    PerDcompAnnotationViewSet,
)

router = DefaultRouter()
router.register(r"", PerDcompViewSet, basename="perdcomp")

# Custom paths for nested resources
urlpatterns = [
    path("status-report/", status_report, name="status-report"),
    path("<uuid:public_id>/deadline-history/", deadline_history, name="deadline-history"),
    path("deadline-preview/", preview, name="deadline-preview"),
    path("upcoming-report/", upcoming_report, name="upcoming-report"),
    # Annotations with perdcomp_id as parameter
    path(
        "annotations/by-perdcomp/<uuid:perdcomp_id>/",
        PerDcompAnnotationViewSet.as_view({"post": "create", "get": "list"}),
        name="perdcomp-annotations",
    ),
    path(
        "annotations/<uuid:annotation_id>/",
        PerDcompAnnotationViewSet.as_view(
            {
                "put": "update",
                "patch": "partial_update",
                "delete": "destroy",
            }
        ),
        name="perdcomp-annotation-detail",
    ),
    path("", include(router.urls)),
]
