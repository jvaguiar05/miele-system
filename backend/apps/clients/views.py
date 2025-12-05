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
from common.shared.models import Annotation
from .serializers import (
    ClientSerializer,
    ClientBasicSerializer,
    ClientSensitiveSerializer,
    AddressSerializer,
    ClientAnnotationSerializer,
)
from common.shared.permissions import (
    IsOwnerOrAdminForAnnotations,
)


class PingView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"ok": True})


@extend_schema(
    tags=["Clientes"],
    summary="Gerenciamento de clientes",
    description="""Endpoints para CRUD completo de clientes. 
    
    **POST**: Cria cliente e sempre cria um endereço (mesmo que vazio se não fornecido). 
    Use campos planos para o endereço (logradouro, numero, bairro, municipio, uf, cep).
    
    **PUT**: Atualiza cliente e endereço completamente. Use os mesmos campos planos do endereço.
    JSONFields vazios podem ser passados como strings vazias "" (serão convertidos automaticamente).
    """,
    examples=[
        OpenApiExample(
            "PUT - Atualização completa do cliente",
            value={
                "razao_social": "Empresa Atualizada LTDA",
                "nome_fantasia": "Nova Fantasia",
                "cnpj": "12.345.678/0001-90",
                "inscricao_estadual": "987.654.321.098",
                "inscricao_municipal": "1122334455",
                "tipo_empresa": "LTDA",
                "recuperacao_judicial": False,
                "telefone_comercial": "(11) 8888-7777",
                "email_comercial": "novo@exemplo.com",
                "website": "https://www.novosite.com",
                "telefone_contato": "(11) 6666-5555",
                "email_contato": "contato@novosite.com",
                "quadro_societario": [
                    {"nome": "Pedro Costa", "cargo": "Sócio-Administrador"},
                    {"nome": "Ana Silva", "cargo": "Sócia"},
                ],
                "responsavel_financeiro": "Ana Silva",
                "contador_responsavel": "Roberto Contador",
                "atividades": [
                    {"cnae": "6201-5/00", "descricao": "Desenvolvimento de software"},
                    {"cnae": "7210-0/00", "descricao": "Consultoria em TI"},
                ],
                "regime_tributacao": "lucro_real",
                "contrato_social": "Contrato atualizado em 2024",
                "ultima_alteracao_contratual": "2024-01-15",
                "rg_cpf_socios": "Pedro: CPF 987.654.321-00",
                "certificado_digital": "Válido até 31/12/2025",
                "autorizado_para_envio": True,
                "client_status": "active",
                "is_active": True,
                # Atualizar endereço também
                "logradouro": "Av. Paulista",
                "numero": "1000",
                "complemento": "Conj. 2001",
                "bairro": "Bela Vista",
                "municipio": "São Paulo",
                "uf": "SP",
                "cep": "01310-100",
            },
        ),
    ],
)
class ClientViewSet(AutoApprovalFieldsMixin, viewsets.ModelViewSet):
    """
    ViewSet para gerenciamento de clientes com criação automática de endereço.

    POST: Cria cliente e sempre cria um endereço (mesmo que vazio se dados não fornecidos).
    Forneça os dados do cliente junto com os campos opcionais do endereço
    (logradouro, numero, bairro, municipio, uf, cep).

    PUT: Atualiza cliente e endereço automaticamente. Use os mesmos campos planos
    do endereço para atualizar o endereço existente.
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
        """Filtrar apenas clientes não excluídos e incluir endereço."""
        return Client.objects.filter(deleted_at__isnull=True).select_related("address")

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
        """Soft delete com data de exclusão e endereço associado."""
        instance.soft_delete()

    @extend_schema(
        summary="Criar cliente com endereço",
        description="Cria um novo cliente junto com seu endereço automaticamente. Todos os campos do cliente estão disponíveis, incluindo dados do endereço.",
        examples=[
            OpenApiExample(
                "Exemplo completo com todos os campos",
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
                    # Dados societários (JSONFields - use arrays/objects)
                    "quadro_societario": [
                        {"nome": "João Silva", "cargo": "Sócio-Administrador"},
                        {"nome": "Maria Santos", "cargo": "Sócia"},
                    ],
                    "responsavel_financeiro": "Maria Santos",
                    "contador_responsavel": "Carlos Oliveira",
                    # Dados fiscais
                    "atividades": [
                        {
                            "cnae": "6201-5/00",
                            "descricao": "Desenvolvimento de software sob encomenda",
                        },
                        {
                            "cnae": "6202-3/00",
                            "descricao": "Desenvolvimento e licenciamento de programas de computador customizáveis",
                        },
                    ],
                    "regime_tributacao": "lucro_presumido",
                    # Documentos
                    "contrato_social": "Contrato registrado em 01/01/2023",
                    "ultima_alteracao_contratual": "2023-06-15",
                    "rg_cpf_socios": "João: CPF 123.456.789-00",
                    "certificado_digital": "Válido até 31/12/2024",
                    # Controles
                    "autorizado_para_envio": True,
                    "client_status": "active",
                    "is_active": True,
                    # Dados do endereço (todos opcionais)
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
                "Exemplo mínimo (apenas campos obrigatórios)",
                value={
                    "razao_social": "Empresa Simples LTDA",
                    "cnpj": "98.765.432/0001-10",
                    # JSONFields podem ser omitidos (usarão defaults) ou vazios:
                    "quadro_societario": [],
                    "atividades": [],
                    # Endereço será criado vazio automaticamente
                },
            ),
            OpenApiExample(
                "Exemplo com strings vazias (serão convertidas)",
                value={
                    "razao_social": "Teste de Conversão LTDA",
                    "cnpj": "11.222.333/0001-44",
                    "nome_fantasia": "Teste",
                    # Strings vazias serão convertidas automaticamente:
                    "quadro_societario": "",  # Vira []
                    "atividades": "",  # Vira []
                    # Endereço com campos vazios
                    "logradouro": "",
                    "numero": "",
                    "bairro": "",
                    "municipio": "",
                    "uf": "",
                    "cep": "",
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
    tags=["Clientes - Anotações"],
    summary="Gerenciamento de anotações de clientes",
    description="Endpoints para CRUD de anotações feitas por usuários em clientes.",
)
class ClientAnnotationViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gerenciamento de anotações de clientes.

    **Características importantes:**
    - Cada usuário pode ter MÚLTIPLAS anotações por cliente
    - O campo 'content' é um objeto JSON que permite estruturas flexíveis
    - Usuários podem ver todas as anotações de todos os usuários
    - Usuários só podem editar/deletar suas próprias anotações

    **Endpoints:**
    - POST /api/v1/clients/annotations/by-client/{client_id}/ - Criar nova anotação para cliente
    - GET /api/v1/clients/annotations/by-client/{client_id}/ - Listar todas as anotações do cliente
    - PUT /api/v1/clients/annotations/{annotation_id}/ - Atualizar anotação completa (apenas próprias)
    - PATCH /api/v1/clients/annotations/{annotation_id}/ - Atualizar apenas campo 'text' (apenas próprias)
    - DELETE /api/v1/clients/annotations/{annotation_id}/ - Excluir anotação (apenas próprias)
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
        """Filtrar anotações baseado no contexto da URL."""
        from django.contrib.contenttypes.models import ContentType

        client_ct = ContentType.objects.get(app_label="clients", model="client")
        queryset = Annotation.objects.filter(
            deleted_at__isnull=True, content_type=client_ct
        )

        # Se há client_id na URL (para list/create), filtrar por cliente
        client_id = self.kwargs.get("client_id")
        if client_id:
            try:
                client = Client.objects.get(
                    public_id=client_id, deleted_at__isnull=True
                )
                queryset = queryset.filter(object_id=client.id)
            except Client.DoesNotExist:
                queryset = queryset.none()

        # Usuários podem ver todas as anotações, mas só podem editar/deletar as próprias
        # A permissão de edição/deleção é controlada pelo IsOwnerOrAdminForAnnotations

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
        summary="Criar nova anotação para cliente",
        description="""
        Cria uma nova anotação para um cliente específico.
        
        **Novo comportamento:** Usuários podem criar múltiplas anotações para o mesmo cliente.
        Cada POST criará uma nova anotação independente.
        
        O client_id deve ser fornecido na URL como parâmetro.
        O content deve ser um objeto JSON com a estrutura desejada.
        """,
        request=ClientAnnotationSerializer,
        responses={
            201: OpenApiResponse(description="Anotação criada com sucesso"),
            400: OpenApiResponse(description="Dados inválidos ou anotação já existe"),
            404: OpenApiResponse(description="Cliente não encontrado"),
        },
        examples=[
            OpenApiExample(
                "Exemplo de requisição",
                value={
                    "content": {
                        "text": "Esta é uma anotação importante sobre o cliente.",
                        "priority": "high",
                        "tags": ["importante", "urgente"],
                        "metadata": {"created_by": "system", "category": "observacao"},
                    }
                },
            )
        ],
    )
    def create(self, request, *args, **kwargs):
        """Criar nova anotação com client_id obtido da URL."""
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

        # Adicionar entity_type e entity_id aos dados
        data = request.data.copy()
        data["entity_type"] = "client"
        data["entity_id"] = str(client_id)

        # Usar o serializer normal para criação
        serializer = ClientAnnotationSerializer(data=data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        annotation = serializer.save()

        # Retornar resposta de criação
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

    @extend_schema(
        summary="Obter anotação específica do cliente",
        description="Obtém uma anotação específica de um cliente. O content retornado é um objeto JSON estruturado.",
        responses={
            200: OpenApiResponse(
                description="Anotação encontrada",
                examples=[
                    OpenApiExample(
                        "Exemplo de resposta",
                        value={
                            "id": "123e4567-e89b-12d3-a456-426614174000",
                            "entity_name": "Empresa Exemplo LTDA",
                            "user_name": "usuario",
                            "content": {
                                "text": "Anotação sobre o cliente",
                                "priority": "high",
                                "tags": ["importante"],
                                "metadata": {"category": "observacao"},
                            },
                            "created_at": "2023-01-01T12:00:00Z",
                            "updated_at": "2023-01-01T12:00:00Z",
                        },
                    )
                ],
            ),
            404: OpenApiResponse(description="Cliente ou anotação não encontrados"),
        },
    )
    def retrieve(self, request, *args, **kwargs):
        """Obter anotação específica."""
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(
        summary="Atualizar completamente anotação do cliente",
        description="""Atualiza completamente uma anotação de cliente. O content deve ser um objeto JSON completo.
        
        **Importante:** Esta operação substitui todo o conteúdo da anotação. Use PATCH para atualizações parciais.
        """,
        request=ClientAnnotationSerializer,
        responses={
            201: OpenApiResponse(description="Anotação criada com sucesso"),
            400: OpenApiResponse(description="Dados inválidos"),
            404: OpenApiResponse(description="Cliente não encontrado"),
            409: OpenApiResponse(
                description="Anotação já existe para este usuário e cliente"
            ),
        },
        examples=[
            OpenApiExample(
                "Exemplo de requisição",
                value={
                    "content": {
                        "text": "Texto da anotação atualizada",
                        "priority": "medium",
                        "tags": ["atualizada", "revisada"],
                        "metadata": {
                            "updated_by": "user",
                            "category": "nota",
                            "version": 2,
                        },
                    }
                },
            )
        ],
    )
    def update(self, request, *args, **kwargs):
        """Atualização completa da anotação."""
        # Validar que content está presente e é um objeto válido
        if "content" not in request.data:
            return Response(
                {"error": "Campo 'content' é obrigatório."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        content = request.data.get("content")
        if not isinstance(content, dict):
            return Response(
                {"error": "Campo 'content' deve ser um objeto JSON."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # For individual annotation operations, update directly
        instance = self.get_object()
        instance.content = content
        instance.save()

        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @extend_schema(
        summary="Atualizar parcialmente anotação do cliente",
        description="""Atualiza apenas o campo 'text' dentro do conteúdo da anotação do cliente.
        
        **Importante:** Este endpoint permite apenas a atualização do campo 'text' dentro do objeto 'content'.
        Outros campos do conteúdo não serão modificados. Para atualizações completas, use PUT.
        """,
        request=ClientAnnotationSerializer,
        responses={
            200: OpenApiResponse(description="Anotação atualizada com sucesso"),
            400: OpenApiResponse(description="Dados inválidos"),
            404: OpenApiResponse(description="Cliente ou anotação não encontrados"),
        },
        examples=[
            OpenApiExample(
                "Atualização parcial do texto",
                value={"content": {"text": "Texto atualizado da anotação"}},
            )
        ],
    )
    def partial_update(self, request, *args, **kwargs):
        """Atualização parcial da anotação - apenas campo 'text' do content."""
        # Validar que apenas o campo 'text' do content está sendo atualizado
        if "content" in request.data:
            content = request.data.get("content")
            if not isinstance(content, dict):
                return Response(
                    {"error": "Campo 'content' deve ser um objeto JSON."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Verificar se apenas 'text' está sendo enviado
            allowed_fields = {"text"}
            provided_fields = set(content.keys())
            invalid_fields = provided_fields - allowed_fields

            if invalid_fields:
                return Response(
                    {
                        "error": f"PATCH permite apenas o campo 'text' dentro de 'content'. Campos inválidos: {list(invalid_fields)}"
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if "text" not in content:
                return Response(
                    {"error": "Campo 'text' é obrigatório em PATCH."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            return Response(
                {"error": "Campo 'content' com 'text' é obrigatório em PATCH."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Obter a anotação existente e fazer merge apenas do campo 'text'
        annotation = self.get_object()
        current_content = annotation.content or {}

        # Atualizar apenas o campo 'text', mantendo outros campos
        updated_content = current_content.copy()
        updated_content["text"] = content["text"]

        # Atualizar diretamente a anotação
        annotation.content = updated_content
        annotation.save()

        # Retornar resposta serializada
        serializer = self.get_serializer(annotation)
        return Response(serializer.data)

    @extend_schema(
        summary="Excluir anotação do cliente",
        description="Exclui uma anotação específica de um cliente (soft delete).",
        responses={
            204: OpenApiResponse(description="Anotação excluída com sucesso"),
            404: OpenApiResponse(description="Anotação não encontrada"),
        },
    )
    def destroy(self, request, *args, **kwargs):
        """Excluir anotação."""
        return super().destroy(request, *args, **kwargs)
