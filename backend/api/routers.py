from django.urls import include, path
from rest_framework.routers import DefaultRouter

router = DefaultRouter()

urlpatterns = [
    path("", include(router.urls)),
    path("auth/", include("apps.identity.urls.auth")),
    path("users/", include("apps.identity.urls.users")),
    path("admin/", include("apps.identity.urls.admin")),
    path("admin/", include("apps.admin_backoffice.urls")),
    path("clients/", include("apps.clients.urls")),
    path("perdcomps/", include("apps.perdcomps.urls")),
]
