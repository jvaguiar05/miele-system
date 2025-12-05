from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    PerDcompViewSet,
    PerDcompAttachedFileViewSet,
    PerDcompAnnotationViewSet,
)

router = DefaultRouter()
router.register(r"", PerDcompViewSet, basename="perdcomp")

# Custom paths for nested resources
urlpatterns = [
    # Nested attached files routes
    path(
        "<uuid:perdcomp_id>/attached-files/",
        PerDcompAttachedFileViewSet.as_view({"post": "create", "get": "list"}),
        name="perdcomp-attached-files",
    ),
    path(
        "<uuid:perdcomp_id>/attached-files/<uuid:pk>/",
        PerDcompAttachedFileViewSet.as_view(
            {
                "get": "retrieve",
                "put": "update",
                "patch": "partial_update",
                "delete": "destroy",
            }
        ),
        name="perdcomp-attached-file-detail",
    ),
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
