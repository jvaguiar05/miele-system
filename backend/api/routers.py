from django.urls import include, path
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
# Example: router.register(r'clients', clients_views.ClientViewSet)

urlpatterns = [
    path("", include(router.urls)),
    path("auth/", include("apps.identity.urls")),
    path("clients/", include("apps.clients.urls")),
    path("perdcomps/", include("apps.perdcomps.urls")),
]
