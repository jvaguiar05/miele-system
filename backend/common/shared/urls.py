"""
URLs para módulos compartilhados.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter


app_name = "shared"

# Router para ViewSets
router = DefaultRouter()

urlpatterns = [
    path("", include(router.urls)),
]
