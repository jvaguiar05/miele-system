"""
URLs para módulos compartilhados.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import AttachedFileViewSet

app_name = "shared"

# Router para ViewSets
router = DefaultRouter()
router.register(r"attached-files", AttachedFileViewSet, basename="attached-files")

urlpatterns = [
    path("", include(router.urls)),
]
