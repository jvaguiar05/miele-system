from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import LossCompensationViewSet

router = DefaultRouter()
router.register(r'', LossCompensationViewSet, basename='losscompensation')

urlpatterns = [
    path('', include(router.urls)),
]
