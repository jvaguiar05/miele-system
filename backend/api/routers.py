from django.urls import include, path
from rest_framework.routers import DefaultRouter

router = DefaultRouter()

urlpatterns = [
    path("", include(router.urls)),
    path("auth/", include("apps.identity.urls.auth")),
    path("users/", include("apps.identity.urls.users")),
    path("admin/", include("apps.identity.urls.admin")),
    path("clients/", include("apps.clients.urls")),
    path("perdcomps/", include("apps.perdcomps.urls")),
    path("dashboard/", include("apps.clients.urls_dashboard")),
    path("activities/", include("common.audit.urls")),
    path("shared/", include("common.shared.urls")),
]
