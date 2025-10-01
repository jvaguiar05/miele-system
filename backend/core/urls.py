from common.observability.health import live, ready
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/live", live),
    path("health/ready", ready),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path("api/v1/", include("api.routers")),
    path("api/v1/clients/", include("apps.clients.urls")),
    path("api/v1/perdcomps/", include("apps.perdcomps.urls")),
]
