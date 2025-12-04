from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ClientViewSet,
    ClientAnnotationViewSet,
    ClientAttachedFileViewSet,
)

router = DefaultRouter()
router.register(r"clients", ClientViewSet, basename="client")

# Custom paths for nested resources
urlpatterns = [
    # Nested attached files routes
    path(
        "clients/<uuid:client_pk>/attached-files/",
        ClientAttachedFileViewSet.as_view({"post": "create", "get": "list"}),
        name="client-attached-files",
    ),
    path(
        "clients/<uuid:client_pk>/attached-files/<uuid:pk>/",
        ClientAttachedFileViewSet.as_view(
            {
                "get": "retrieve",
                "put": "update",
                "patch": "partial_update",
                "delete": "destroy",
            }
        ),
        name="client-attached-file-detail",
    ),
    # Legacy route for attached files (without client context)
    path(
        "attached-files/",
        ClientAttachedFileViewSet.as_view({"get": "list"}),
        name="attached-files-list",
    ),
    path(
        "attached-files/<uuid:pk>/",
        ClientAttachedFileViewSet.as_view(
            {
                "get": "retrieve",
                "put": "update",
                "patch": "partial_update",
                "delete": "destroy",
            }
        ),
        name="attached-file-detail",
    ),
    # Annotations with client_id as parameter
    path(
        "annotations/by-client/<uuid:client_id>/",
        ClientAnnotationViewSet.as_view({"post": "create", "get": "list"}),
        name="client-annotations",
    ),
    path(
        "annotations/<uuid:annotation_id>/",
        ClientAnnotationViewSet.as_view(
            {
                "put": "update",
                "patch": "partial_update",
                "delete": "destroy",
            }
        ),
        name="client-annotation-detail",
    ),
    path("", include(router.urls)),
]
