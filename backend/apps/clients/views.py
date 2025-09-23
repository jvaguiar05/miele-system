from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from common.approvals.mixins import RequiresApprovalMixin
from .models import Client
from .serializers import ClientSerializer
from .permissions import ClientPermissions


class PingView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"ok": True})


class ClientViewSet(RequiresApprovalMixin, viewsets.ModelViewSet):
    """
    ViewSet para clientes com aprovação automática para campos sensíveis.

    Campos sensíveis (requerem aprovação):
    - cnpj, razao_social, status, is_active

    Campos não sensíveis (alteração direta):
    - nome_fantasia, email, telefone
    """

    queryset = Client.objects.all()
    serializer_class = ClientSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["status", "is_active"]
    search_fields = ["cnpj", "razao_social", "nome_fantasia"]
    ordering_fields = ["created_at", "razao_social"]
    ordering = ["-created_at"]

    # Configuração para aprovação automática
    approval_resource_type = "clients.Client"
    # Os campos sensíveis são obtidos automaticamente de SENSITIVE_FIELDS_CONFIG

    def get_queryset(self):
        """Filtrar apenas clientes não excluídos."""
        return Client.objects.filter(deleted_at__isnull=True)

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        """
        Ativar cliente - requer aprovação.
        """
        client = self.get_object()

        # Simular alteração de campo sensível (is_active)
        # Isso será interceptado pelo mixin e criará approval_request
        fake_request_data = {"is_active": True}
        request.data = fake_request_data

        return self._create_approval_request(request, "activate", pk=pk)

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        """
        Desativar cliente - requer aprovação.
        """
        client = self.get_object()

        # Simular alteração de campo sensível (is_active)
        fake_request_data = {"is_active": False}
        request.data = fake_request_data

        return self._create_approval_request(request, "deactivate", pk=pk)

    @action(detail=True, methods=["delete"])
    def soft_delete(self, request, pk=None):
        """
        Exclusão lógica - requer aprovação.
        """
        return self._create_approval_request(request, "destroy", pk=pk)

    @action(detail=False, methods=["get"])
    def pending_approvals(self, request):
        """
        Listar clientes com aprovações pendentes.
        """
        from common.approvals.models import ApprovalRequest

        pending_requests = ApprovalRequest.objects.filter(
            resource_type="clients.Client", status=ApprovalRequest.Status.PENDING
        ).select_related("requested_by")

        data = []
        for approval in pending_requests:
            try:
                client = Client.objects.get(pk=approval.resource_id)
                data.append(
                    {
                        "approval_id": approval.id,
                        "client": {
                            "id": client.id,
                            "razao_social": client.razao_social,
                            "cnpj": client.cnpj,
                        },
                        "subject": approval.subject,
                        "requested_by": approval.requested_by.username,
                        "created_at": approval.created_at,
                    }
                )
            except Client.DoesNotExist:
                continue

        return Response(data)
