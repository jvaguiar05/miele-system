from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    PerDcompViewSet,
    PerDcompAttachedFileViewSet,
    PerDcompAnnotationViewSet,
)

router = DefaultRouter()
router.register(r"", PerDcompViewSet, basename="perdcomp")
router.register(
    r"attached-files", PerDcompAttachedFileViewSet, basename="perdcomp-attached-file"
)
# Remove the old annotations route since we'll use a custom path pattern

# Custom path for annotations with perdcomp_id as parameter
urlpatterns = [
    path(
        "annotations/<uuid:perdcomp_id>/",
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
