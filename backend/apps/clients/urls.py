from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ClientViewSet,
    AddressViewSet,
    ClientAnnotationViewSet,
    ClientAttachedFileViewSet,
)

router = DefaultRouter()
router.register(r"clients", ClientViewSet, basename="client")
router.register(r"addresses", AddressViewSet, basename="address")
# Remove the old annotations route since we'll use a custom path pattern
router.register(
    r"attached-files", ClientAttachedFileViewSet, basename="clientattachedfile"
)

# Custom path for annotations with client_id as parameter
urlpatterns = [
    path(
        "clients/annotations/<uuid:client_id>/",
        ClientAnnotationViewSet.as_view({"post": "create", "get": "list"}),
        name="client-annotations",
    ),
    path(
        "clients/annotations/<uuid:client_id>/<uuid:annotation_id>/",
        ClientAnnotationViewSet.as_view(
            {
                "get": "retrieve",
                "put": "update",
                "patch": "partial_update",
                "delete": "destroy",
            }
        ),
        name="client-annotation-detail",
    ),
    path("", include(router.urls)),
]
