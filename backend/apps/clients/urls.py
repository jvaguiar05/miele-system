from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ClientViewSet,
    ClientAnnotationViewSet,
)
from .contract_views import client_contracts, client_contract_detail

router = DefaultRouter()
router.register(r"clients", ClientViewSet, basename="client")

# Custom paths for nested resources
urlpatterns = [
    path("<uuid:client_id>/contracts/", client_contracts, name="client-contracts"),
    path("<uuid:client_id>/contracts/<uuid:contract_id>/", client_contract_detail, name="client-contract-detail"),
    path("", include(router.urls)),
    # Annotations with client_id as parameter
    path(
        "annotations/by-client/<uuid:client_id>/",
        ClientAnnotationViewSet.as_view({"post": "create", "get": "list"}),
        name="client-annotations",
    ),
    path(
        "annotations/<uuid:annotation_id>/",
        ClientAnnotationViewSet.as_view(
            {
                "put": "update",
                "patch": "partial_update",
                "delete": "destroy",
            }
        ),
        name="client-annotation-detail",
    ),
    path(
        "lookup-cnpj/",
        ClientViewSet.as_view({"get": "lookup_cnpj"}),
        name="client-lookup-cnpj",
    ),
]
