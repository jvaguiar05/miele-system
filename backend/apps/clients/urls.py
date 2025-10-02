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
router.register(r"annotations", ClientAnnotationViewSet, basename="clientannotation")
router.register(
    r"attached-files", ClientAttachedFileViewSet, basename="clientattachedfile"
)

urlpatterns = [
    path("", include(router.urls)),
]
