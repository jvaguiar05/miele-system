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
from .models import Client, Address, ClientAnnotation, ClientAttachedFile
from .serializers import (
    ClientSerializer,
    ClientBasicSerializer,
    ClientSensitiveSerializer,
    AddressSerializer,
    ClientAnnotationSerializer,
    ClientAttachedFileSerializer,
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
    filterset_fields = ["is_active"]
    search_fields = ["cnpj", "razao_social", "nome_fantasia"]
    ordering_fields = ["created_at", "razao_social"]
    ordering = ["-created_at"]

    # Configuração para RequiresApprovalMixin
    approval_resource_type = "clients.Client"

    def get_queryset(self):
        """Filtrar apenas clientes não excluídos."""
        return Client.objects.filter(deleted_at__isnull=True)

    def get_object(self):
        """Buscar objeto por public_id em vez de id."""
        queryset = self.filter_queryset(self.get_queryset())
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        lookup_value = self.kwargs[lookup_url_kwarg]

        try:
            obj = queryset.get(public_id=lookup_value)
        except Client.DoesNotExist:
            from django.http import Http404

            raise Http404("Cliente não encontrado.")

        self.check_object_permissions(self.request, obj)
        return obj

    def get_permissions(self):
        """Apenas admins podem deletar."""
        if self.action == "destroy":
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
        summary="Atualizar anotações do cliente (DEPRECATED)",
        description="DEPRECATED: Use o endpoint de ClientAnnotationViewSet. Este endpoint será removido em versões futuras.",
        request=ClientAnnotationSerializer,
        responses={
            200: OpenApiResponse(description="Anotações atualizadas com sucesso"),
            404: OpenApiResponse(description="Cliente não encontrado"),
        },
        deprecated=True,
    )
    @action(
        detail=True,
        methods=["patch"],
        serializer_class=ClientAnnotationSerializer,
        url_path="annotations",
    )
    def update_annotations(self, request, pk=None):
        """
        DEPRECATED: Atualizar apenas anotações (use ClientAnnotationViewSet).
        PATCH /api/clients/{id}/annotations/
        """
        # Esta funcionalidade foi movida para o ClientAnnotationViewSet
        return Response(
            {
                "message": "Este endpoint foi descontinuado. Use o ClientAnnotationViewSet para gerenciar anotações.",
                "deprecated": True,
            },
            status=status.HTTP_410_GONE,
        )

    @extend_schema(
        tags=["Clients"],
        summary="Atualizar dados sensíveis do cliente",
        description="Atualiza dados sensíveis que requerem aprovação administrativa. Cria automaticamente uma solicitação de aprovação.",
        request=ClientSensitiveSerializer,
        responses={
            202: OpenApiResponse(
                description="Solicitação de aprovação criada",
                examples=[
                    OpenApiExample(
                        "Aguardando aprovação",
                        value={
                            "message": "Solicitação de alteração criada. Aguardando aprovação.",
                            "requires_approval": True,
                        },
                    )
                ],
            ),
            404: OpenApiResponse(description="Cliente não encontrado"),
        },
    )
    @action(
        detail=True,
        methods=["patch"],
        serializer_class=ClientSensitiveSerializer,
        url_path="sensitive-data",
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

        return Response(
            {
                "message": "Solicitação de alteração criada. Aguardando aprovação.",
                "requires_approval": True,
            },
            status=status.HTTP_202_ACCEPTED,
        )


@extend_schema(
    tags=["Addresses"],
    summary="Gerenciamento de endereços",
    description="Endpoints para CRUD de endereços de clientes.",
)
class AddressViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gerenciamento de endereços.
    """

    serializer_class = AddressSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["uf", "municipio"]
    search_fields = ["logradouro", "bairro", "municipio", "cep"]
    ordering_fields = ["created_at", "municipio"]
    ordering = ["-created_at"]

    def get_queryset(self):
        """Filtrar apenas endereços não excluídos."""
        return Address.objects.filter(deleted_at__isnull=True)

    def get_object(self):
        """Buscar objeto por public_id em vez de id."""
        queryset = self.filter_queryset(self.get_queryset())
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        lookup_value = self.kwargs[lookup_url_kwarg]

        try:
            obj = queryset.get(public_id=lookup_value)
        except Address.DoesNotExist:
            from django.http import Http404

            raise Http404("Endereço não encontrado.")

        self.check_object_permissions(self.request, obj)
        return obj


@extend_schema(
    tags=["Client Annotations"],
    summary="Gerenciamento de anotações de clientes",
    description="Endpoints para CRUD de anotações feitas por usuários em clientes.",
)
class ClientAnnotationViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gerenciamento de anotações de clientes.
    """

    serializer_class = ClientAnnotationSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["client", "user"]
    search_fields = ["content", "client__razao_social"]
    ordering_fields = ["created_at"]
    ordering = ["-created_at"]

    def get_queryset(self):
        """Filtrar apenas anotações não excluídas."""
        return ClientAnnotation.objects.filter(deleted_at__isnull=True)

    def get_object(self):
        """Buscar objeto por public_id em vez de id."""
        queryset = self.filter_queryset(self.get_queryset())
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        lookup_value = self.kwargs[lookup_url_kwarg]

        try:
            obj = queryset.get(public_id=lookup_value)
        except ClientAnnotation.DoesNotExist:
            from django.http import Http404

            raise Http404("Anotação não encontrada.")

        self.check_object_permissions(self.request, obj)
        return obj

    def perform_create(self, serializer):
        """Automaticamente definir o usuário como o usuário logado."""
        serializer.save()


@extend_schema(
    tags=["Client Attached Files"],
    summary="Gerenciamento de arquivos anexados a clientes",
    description="Endpoints para CRUD de arquivos anexados a clientes.",
)
class ClientAttachedFileViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gerenciamento de arquivos anexados a clientes.
    """

    serializer_class = ClientAttachedFileSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["client", "uploaded_by", "file_type"]
    search_fields = ["file_name", "description", "client__razao_social"]
    ordering_fields = ["created_at", "file_name"]
    ordering = ["-created_at"]

    def get_queryset(self):
        """Filtrar apenas arquivos não excluídos."""
        return ClientAttachedFile.objects.filter(deleted_at__isnull=True)

    def get_object(self):
        """Buscar objeto por public_id em vez de id."""
        queryset = self.filter_queryset(self.get_queryset())
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        lookup_value = self.kwargs[lookup_url_kwarg]

        try:
            obj = queryset.get(public_id=lookup_value)
        except ClientAttachedFile.DoesNotExist:
            from django.http import Http404

            raise Http404("Arquivo não encontrado.")

        self.check_object_permissions(self.request, obj)
        return obj

    def perform_create(self, serializer):
        """Automaticamente definir o usuário como o uploader."""
        serializer.save()
