from django.urls import include, path
from rest_framework.routers import DefaultRouter

router = DefaultRouter()

urlpatterns = [
    path("", include(router.urls)),
    path("identity/", include("apps.identity.urls")),
    path("clients/", include("apps.clients.urls")),
    path("perdcomps/", include("apps.perdcomps.urls")),
    path("admin/", include("apps.admin_backoffice.urls")),
]
