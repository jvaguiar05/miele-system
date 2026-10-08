from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ClientViewSet,
    ClientAnnotationViewSet,
)
from .contract_views import client_contracts, client_contract_detail
from apps.perdcomps import import_views

router = DefaultRouter()
router.register(r"clients", ClientViewSet, basename="client")

# Custom paths for nested resources
urlpatterns = [
    path("<uuid:client_id>/perdcomp-imports/preview/", import_views.preview),
    path("<uuid:client_id>/perdcomp-imports/confirm/", import_views.confirm),
    path("<uuid:client_id>/perdcomp-imports/preview-file/", import_views.preview_file),
    path("<uuid:client_id>/perdcomp-imports/documents/", import_views.documents),
    path("<uuid:client_id>/perdcomp-imports/credit-chain/", import_views.credit_chain),
    path("<uuid:client_id>/perdcomp-imports/reprocess/preview/", import_views.reprocess_preview),
    path("<uuid:client_id>/perdcomp-imports/reprocess/confirm/", import_views.reprocess_confirm),
    path("<uuid:client_id>/perdcomp-imports/sync-drive/", import_views.sync_drive),
    path("<uuid:client_id>/perdcomp-imports/files/<uuid:file_id>/", import_views.original),
    path("<uuid:client_id>/perdcomp-imports/manual/<uuid:issue_id>/file/", import_views.manual_original),
    path("<uuid:client_id>/perdcomp-imports/manual/<uuid:issue_id>/resolve/", import_views.resolve_manual),
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
