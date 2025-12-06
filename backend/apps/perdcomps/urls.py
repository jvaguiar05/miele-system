from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    PerDcompViewSet,
    PerDcompAnnotationViewSet,
)

router = DefaultRouter()
router.register(r"", PerDcompViewSet, basename="perdcomp")

# Custom paths for nested resources
urlpatterns = [
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
