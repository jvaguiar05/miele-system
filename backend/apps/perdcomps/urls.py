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
router.register(
    r"annotations", PerDcompAnnotationViewSet, basename="perdcomp-annotation"
)

urlpatterns = [
    path("", include(router.urls)),
]
