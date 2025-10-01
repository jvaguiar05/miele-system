from rest_framework import viewsets, status, serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from drf_spectacular.utils import extend_schema
from drf_spectacular.openapi import OpenApiResponse, OpenApiExample

from common.approvals.mixins import AutoApprovalFieldsMixin
from common.permissions import IsAdminUser
from .models import Client
from .serializers import (
    ClientSerializer,
    ClientAnnotationSerializer,
    ClientSensitiveSerializer
)
from .permissions import ClientPermissions


class PingView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"ok": True})


@extend_schema(
    tags=["Clients"],
    summary="Gerenciamento de clientes",
    description="Endpoints para CRUD completo de clientes com aprovação automática para campos sensíveis.",
)
class ClientViewSet(AutoApprovalFieldsMixin, viewsets.ModelViewSet):
    """
    ViewSet para gerenciamento de clientes com aprovação automática
    para alterações em campos sensíveis.
    """
    serializer_class = ClientSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['is_active']
    search_fields = ['cnpj', 'razao_social', 'nome_fantasia']
    ordering_fields = ['created_at', 'razao_social']
    ordering = ['-created_at']
    
    # Configuração para RequiresApprovalMixin
    approval_resource_type = 'clients.Client'
    
    def get_queryset(self):
        """Filtrar apenas clientes não excluídos."""
        return Client.objects.filter(deleted_at__isnull=True)
    
    def get_permissions(self):
        """Apenas admins podem deletar."""
        if self.action == 'destroy':
            permission_classes = [IsAdminUser]
        else:
            permission_classes = [IsAuthenticated]
        return [permission() for permission in permission_classes]
    
    def perform_destroy(self, instance):
        """Soft delete com data de exclusão."""
        from django.utils import timezone
        instance.deleted_at = timezone.now()
        instance.is_active = False
        instance.save()
    
    @extend_schema(
        tags=["Clients"],
        summary="Atualizar anotações do cliente",
        description="Atualiza apenas as anotações internas do cliente. Não requer aprovação.",
        request=ClientAnnotationSerializer,
        responses={
            200: OpenApiResponse(description="Anotações atualizadas com sucesso"),
            404: OpenApiResponse(description="Cliente não encontrado"),
        },
    )
    @action(
        detail=True,
        methods=['patch'],
        serializer_class=ClientAnnotationSerializer,
        url_path='annotations'
    )
    def update_annotations(self, request, pk=None):
        """
        Atualizar apenas anotações (não requer aprovação).
        PATCH /api/clients/{id}/annotations/
        """
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        return Response(serializer.data)
    
    @extend_schema(
        tags=["Clients"],
        summary="Atualizar dados sensíveis do cliente",
        description="Atualiza dados sensíveis que requerem aprovação administrativa. Cria automaticamente uma solicitação de aprovação.",
        request=ClientSensitiveSerializer,
        responses={
            202: OpenApiResponse(
                description="Solicitação de aprovação criada",
                examples=[OpenApiExample("Aguardando aprovação", value={"message": "Solicitação de alteração criada. Aguardando aprovação.", "requires_approval": True})],
            ),
            404: OpenApiResponse(description="Cliente não encontrado"),
        },
    )
    @action(
        detail=True,
        methods=['patch'],
        serializer_class=ClientSensitiveSerializer,
        url_path='sensitive-data'
    )
    def update_sensitive_data(self, request, pk=None):
        """
        Atualizar dados sensíveis (requer aprovação automática).
        PATCH /api/clients/{id}/sensitive-data/
        
        Este endpoint usa RequiresApprovalMixin que intercepta automaticamente
        e cria ApprovalRequest ao invés de alterar diretamente.
        """
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        
        # O RequiresApprovalMixin intercepta aqui e cria ApprovalRequest
        serializer.save()
        
        return Response({
            'message': 'Solicitação de alteração criada. Aguardando aprovação.',
            'requires_approval': True
        }, status=status.HTTP_202_ACCEPTED)
