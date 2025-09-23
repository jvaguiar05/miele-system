from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import PingView, ApprovalRequestAdminViewSet

router = DefaultRouter()
router.register(
    r"approval-requests", ApprovalRequestAdminViewSet, basename="approval-requests"
)

urlpatterns = [
    path("ping/", PingView.as_view(), name="admin-ping"),
    path("", include(router.urls)),
]
