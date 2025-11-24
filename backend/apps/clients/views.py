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
from .models import Client, Address
from common.shared.models import Annotation, AttachedFile
from .serializers import (
    ClientSerializer,
    ClientBasicSerializer,
    ClientSensitiveSerializer,
    AddressSerializer,
    ClientAnnotationSerializer,
    ClientAttachedFileSerializer,
)
from common.shared.permissions import (
    IsOwnerOrAdminForAnnotations,
    IsOwnerOrAdminForAttachedFiles,
)


class PingView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"ok": True})


@extend_schema(
    tags=["Clientes"],
    summary="Gerenciamento de clientes",
    description="Endpoints para CRUD completo de clientes. No POST, o endereço é criado automaticamente junto com o cliente.",
)
class ClientViewSet(AutoApprovalFieldsMixin, viewsets.ModelViewSet):
    """
    ViewSet para gerenciamento de clientes com criação automática de endereço.

    POST: Cria cliente e endereço automaticamente. Forneça os dados do cliente
    junto com os campos do endereço (logradouro, numero, bairro, municipio, uf, cep).
    """

    serializer_class = ClientSerializer
    lookup_field = "public_id"
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
        """Buscar objeto por public_id."""
        queryset = self.filter_queryset(self.get_queryset())
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        lookup_value = self.kwargs[lookup_url_kwarg]

        try:
            obj = queryset.get(**{self.lookup_field: lookup_value})
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
        summary="Criar cliente com endereço",
        description="Cria um novo cliente junto com seu endereço automaticamente. Todos os campos do cliente estão disponíveis, incluindo dados do endereço.",
        examples=[
            OpenApiExample(
                "Exemplo completo",
                value={
                    # Dados principais do cliente
                    "razao_social": "Empresa Exemplo LTDA",
                    "nome_fantasia": "Empresa Exemplo",
                    "cnpj": "12.345.678/0001-90",
                    "inscricao_estadual": "123.456.789.012",
                    "inscricao_municipal": "9876543210",
                    "tipo_empresa": "LTDA",
                    "recuperacao_judicial": False,
                    # Contatos comerciais
                    "telefone_comercial": "(11) 1234-5678",
                    "email_comercial": "contato@exemplo.com",
                    "website": "https://www.exemplo.com",
                    # Contatos diretos
                    "telefone_contato": "(11) 9999-8888",
                    "email_contato": "financeiro@exemplo.com",
                    # Dados societários
                    "quadro_societario": [
                        {"nome": "João Silva", "participacao": "50%"}
                    ],
                    "cargos": {"diretor": "João Silva", "gerente": "Maria Santos"},
                    "responsavel_financeiro": "Maria Santos",
                    "contador_responsavel": "Carlos Oliveira",
                    # Dados fiscais
                    "cnaes": ["6201-5/00", "6202-3/00"],
                    "regime_tributacao": "lucro_presumido",
                    # Documentos
                    "contrato_social": "Contrato registrado em 01/01/2023",
                    "ultima_alteracao_contratual": "2023-06-15T00:00:00Z",
                    "rg_cpf_socios": "João: CPF 123.456.789-00",
                    "certificado_digital": "Válido até 31/12/2024",
                    # Controles
                    "autorizado_para_envio": True,
                    "atividades": {"principal": "Desenvolvimento de software"},
                    "client_status": "active",
                    "is_active": True,
                    # Dados do endereço (obrigatórios se fornecidos)
                    "logradouro": "Rua das Flores",
                    "numero": "123",
                    "complemento": "Sala 456",
                    "bairro": "Centro",
                    "municipio": "São Paulo",
                    "uf": "SP",
                    "cep": "01234-567",
                },
            ),
            OpenApiExample(
                "Exemplo mínimo",
                value={
                    "razao_social": "Empresa Simples LTDA",
                    "cnpj": "98.765.432/0001-10",
                    "logradouro": "Av. Principal",
                    "numero": "456",
                    "bairro": "Vila Nova",
                    "municipio": "Rio de Janeiro",
                    "uf": "RJ",
                    "cep": "20000-000",
                },
            ),
        ],
        responses={
            201: OpenApiResponse(description="Cliente e endereço criados com sucesso"),
            400: OpenApiResponse(description="Dados inválidos"),
        },
    )
    def create(self, request, *args, **kwargs):
        """Criar cliente com endereço automaticamente."""
        return super().create(request, *args, **kwargs)

    @extend_schema(
        tags=["Clientes"],
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
        tags=["Clientes"],
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
    tags=["Endereços"],
    summary="Gerenciamento de endereços",
    description="Endpoints para CRUD de endereços de clientes.",
)
class AddressViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gerenciamento de endereços.
    """

    serializer_class = AddressSerializer
    lookup_field = "public_id"
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
        """Buscar objeto por public_id."""
        queryset = self.filter_queryset(self.get_queryset())
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        lookup_value = self.kwargs[lookup_url_kwarg]

        try:
            obj = queryset.get(**{self.lookup_field: lookup_value})
        except Address.DoesNotExist:
            from django.http import Http404

            raise Http404("Endereço não encontrado.")

        self.check_object_permissions(self.request, obj)
        return obj


@extend_schema(
    tags=["Clientes - Anotações"],
    summary="Gerenciamento de anotações de clientes",
    description="Endpoints para CRUD de anotações feitas por usuários em clientes.",
)
class ClientAnnotationViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gerenciamento de anotações de clientes.

    Endpoints:
    POST /api/v1/clients/annotations/{client_id}/ - Criar anotação para cliente
    GET /api/v1/clients/annotations/{client_id}/ - Listar anotações do cliente
    GET /api/v1/clients/annotations/{client_id}/{annotation_id}/ - Obter anotação específica
    PUT/PATCH /api/v1/clients/annotations/{client_id}/{annotation_id}/ - Atualizar anotação
    DELETE /api/v1/clients/annotations/{client_id}/{annotation_id}/ - Excluir anotação
    """

    serializer_class = ClientAnnotationSerializer
    lookup_field = "public_id"
    lookup_url_kwarg = "annotation_id"  # Use annotation_id from URL
    permission_classes = [IsOwnerOrAdminForAnnotations]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["user_id"]
    search_fields = ["content"]
    ordering_fields = ["created_at"]
    ordering = ["-created_at"]

    def get_queryset(self):
        """Filtrar anotações do cliente especificado na URL."""
        from django.contrib.contenttypes.models import ContentType
        from common.permissions import IsAdminUser

        client_ct = ContentType.objects.get(app_label="clients", model="client")
        queryset = Annotation.objects.filter(
            deleted_at__isnull=True, content_type=client_ct
        )

        # Filtrar pelo client_id da URL se fornecido
        client_id = self.kwargs.get("client_id")
        if client_id:
            # Verificar se o cliente existe
            try:
                client = Client.objects.get(
                    public_id=client_id, deleted_at__isnull=True
                )
                # Filtrar anotações deste cliente específico
                queryset = queryset.filter(object_id=client.id)
            except Client.DoesNotExist:
                # Se cliente não existe, retornar queryset vazio
                queryset = queryset.none()

        # Se não for admin, filtrar apenas anotações do usuário
        if not IsAdminUser().has_permission(self.request, self):
            queryset = queryset.filter(user_id=self.request.user.id)

        return queryset

    def get_object(self):
        """Buscar objeto por public_id."""
        queryset = self.filter_queryset(self.get_queryset())
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        lookup_value = self.kwargs[lookup_url_kwarg]

        try:
            obj = queryset.get(**{self.lookup_field: lookup_value})
        except Annotation.DoesNotExist:
            from django.http import Http404

            raise Http404("Anotação não encontrada.")

        self.check_object_permissions(self.request, obj)
        return obj

    @extend_schema(
        summary="Criar anotação para cliente",
        description="""
        Cria uma nova anotação para um cliente específico.
        
        O client_id deve ser fornecido na URL como parâmetro.
        """,
        request=ClientAnnotationSerializer,
        responses={
            201: OpenApiResponse(description="Anotação criada com sucesso"),
            400: OpenApiResponse(description="Dados inválidos"),
            404: OpenApiResponse(description="Cliente não encontrado"),
        },
        examples=[
            OpenApiExample(
                "Exemplo de requisição",
                value={"content": "Esta é uma anotação importante sobre o cliente."},
            )
        ],
    )
    def create(self, request, *args, **kwargs):
        """Criar anotação com client_id obtido da URL."""
        # Obter client_id da URL
        client_id = kwargs.get("client_id")

        if not client_id:
            return Response(
                {"error": "client_id é obrigatório na URL."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Verificar se o cliente existe
        try:
            client = Client.objects.get(public_id=client_id, deleted_at__isnull=True)
        except Client.DoesNotExist:
            return Response(
                {"error": "Cliente não encontrado."}, status=status.HTTP_404_NOT_FOUND
            )

        # Serializar dados do request
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Adicionar entity_type e entity_id manualmente
        validated_data = serializer.validated_data
        validated_data["entity_type"] = "client"
        validated_data["entity_id"] = str(client_id)  # Usar o UUID do cliente

        # Chamar o método validate do AnnotationSerializer pai
        annotation_data = AnnotationSerializer().validate(validated_data)

        # Criar a anotação
        annotation = AnnotationSerializer().create(annotation_data)

        # Retornar resposta
        response_serializer = self.get_serializer(annotation)
        headers = self.get_success_headers(response_serializer.data)
        return Response(
            response_serializer.data, status=status.HTTP_201_CREATED, headers=headers
        )

    @extend_schema(
        summary="Listar anotações do cliente",
        description="Lista todas as anotações do cliente especificado.",
        responses={
            200: OpenApiResponse(description="Lista de anotações"),
            404: OpenApiResponse(description="Cliente não encontrado"),
        },
    )
    def list(self, request, *args, **kwargs):
        """Listar anotações do cliente especificado na URL."""
        client_id = kwargs.get("client_id")

        # Verificar se o cliente existe
        try:
            Client.objects.get(public_id=client_id, deleted_at__isnull=True)
        except Client.DoesNotExist:
            return Response(
                {"error": "Cliente não encontrado."}, status=status.HTTP_404_NOT_FOUND
            )

        return super().list(request, *args, **kwargs)

    def perform_create(self, serializer):
        """Automaticamente definir o usuário como o usuário logado."""
        serializer.save()


@extend_schema(
    tags=["Clientes - Arquivos"],
    summary="Gerenciamento de arquivos anexados a clientes",
    description="Endpoints para CRUD de arquivos anexados a clientes.",
)
class ClientAttachedFileViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gerenciamento de arquivos anexados a clientes.
    """

    serializer_class = ClientAttachedFileSerializer
    lookup_field = "public_id"
    permission_classes = [IsOwnerOrAdminForAttachedFiles]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["file_type", "uploaded_by_id"]
    search_fields = ["file_name", "description"]
    ordering_fields = ["created_at", "file_name"]
    ordering = ["-created_at"]

    def get_queryset(self):
        """Filtrar apenas arquivos não excluídos do usuário (ou todos se admin)."""
        from django.contrib.contenttypes.models import ContentType
        from common.permissions import IsAdminUser

        client_ct = ContentType.objects.get(app_label="clients", model="client")
        queryset = AttachedFile.objects.filter(
            deleted_at__isnull=True, content_type=client_ct
        )

        # Se não for admin, filtrar apenas arquivos do usuário
        if not IsAdminUser().has_permission(self.request, self):
            queryset = queryset.filter(uploaded_by_id=self.request.user.id)

        return queryset

    def get_object(self):
        """Buscar objeto por public_id."""
        queryset = self.filter_queryset(self.get_queryset())
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        lookup_value = self.kwargs[lookup_url_kwarg]

        try:
            obj = queryset.get(**{self.lookup_field: lookup_value})
        except AttachedFile.DoesNotExist:
            from django.http import Http404

            raise Http404("Arquivo não encontrado.")

        self.check_object_permissions(self.request, obj)
        return obj

    def perform_create(self, serializer):
        """Automaticamente definir o usuário como o uploader."""
        serializer.save()
