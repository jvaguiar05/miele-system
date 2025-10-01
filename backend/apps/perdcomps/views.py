from rest_framework import viewsets, status
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
from .models import LossCompensation
from .serializers import (
    LossCompensationSerializer,
    LossCompensationAnnotationSerializer,
    LossCompensationSensitiveSerializer
)


class PingView(APIView):
    authentication_classes = []
    permission_classes = []

    @extend_schema(
        tags=["PER/DCOMPs"],
        summary="Verificação de saúde da API PER/DCOMPs",
        description="Endpoint simples para verificar se a API de PER/DCOMPs está funcionando.",
        responses={
            200: OpenApiResponse(
                description="API funcionando corretamente",
                examples=[OpenApiExample("Sucesso", value={"ok": True})],
            )
        },
    )
    def get(self, request):
        return Response({"ok": True})


@extend_schema(
    tags=["PER/DCOMPs"],
    summary="Gerenciamento de PER/DCOMPs",
    description="Endpoints para CRUD completo de perdas e compensações com aprovação automática para campos sensíveis.",
)
class LossCompensationViewSet(AutoApprovalFieldsMixin, viewsets.ModelViewSet):
    """
    ViewSet para gerenciamento de perdas de compensação com aprovação 
    automática para alterações sensíveis.
    """
    serializer_class = LossCompensationSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['loss_type', 'client', 'is_active']
    search_fields = ['reference_number', 'description', 'client__razao_social']
    ordering_fields = ['created_at', 'loss_date', 'loss_amount']
    ordering = ['-created_at']
    
    # Configuração para RequiresApprovalMixin
    approval_resource_type = 'perdcomps.LossCompensation'
    
    def get_queryset(self):
        """Filtrar por usuário e entidades ativas."""
        return LossCompensation.objects.filter(
            deleted_at__isnull=True,
            client__deleted_at__isnull=True
        )
    
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
        tags=["PER/DCOMPs"],
        summary="Atualizar anotações da PER/DCOMP",
        description="Atualiza apenas as anotações internas da perda/compensação. Não requer aprovação.",
        request=LossCompensationAnnotationSerializer,
        responses={
            200: OpenApiResponse(description="Anotações atualizadas com sucesso"),
            404: OpenApiResponse(description="PER/DCOMP não encontrada"),
        },
    )
    @action(
        detail=True,
        methods=['patch'],
        serializer_class=LossCompensationAnnotationSerializer,
        url_path='annotations'
    )
    def update_annotations(self, request, pk=None):
        """
        Atualizar apenas anotações (não requer aprovação).
        PATCH /api/perdcomps/{id}/annotations/
        """
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        return Response(serializer.data)
    
    @extend_schema(
        tags=["PER/DCOMPs"],
        summary="Atualizar dados sensíveis da PER/DCOMP",
        description="Atualiza dados sensíveis que requerem aprovação administrativa. Cria automaticamente uma solicitação de aprovação.",
        request=LossCompensationSensitiveSerializer,
        responses={
            202: OpenApiResponse(
                description="Solicitação de aprovação criada",
                examples=[OpenApiExample("Aguardando aprovação", value={"message": "Solicitação de alteração criada. Aguardando aprovação.", "requires_approval": True})],
            ),
            404: OpenApiResponse(description="PER/DCOMP não encontrada"),
        },
    )
    @action(
        detail=True,
        methods=['patch'],
        serializer_class=LossCompensationSensitiveSerializer,
        url_path='sensitive-data'
    )
    def update_sensitive_data(self, request, pk=None):
        """
        Atualizar dados sensíveis (requer aprovação automática).
        PATCH /api/perdcomps/{id}/sensitive-data/
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
