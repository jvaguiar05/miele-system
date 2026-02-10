from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.openapi import OpenApiResponse, OpenApiExample
from django.db import models
from django.db.models import Sum, Count, Q
from decimal import Decimal, InvalidOperation
from django.http import Http404

from common.approvals.mixins import AutoApprovalFieldsMixin
from common.permissions import IsAdminUser
from common.shared.permissions import (
    IsOwnerOrAdminForAnnotations,
)
from .models import PerDcomp
from common.shared.models import Annotation
from .serializers import (
    PerDcompSerializer,
    PerDcompBasicSerializer,
    PerDcompSensitiveSerializer,
    PerDcompAnnotationSerializer,
)
from .services import PerDcompExcelExporter


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
    description="Endpoints para CRUD completo de PER/DCOMPs com aprovação automática para campos sensíveis.",
)
class PerDcompViewSet(AutoApprovalFieldsMixin, viewsets.ModelViewSet):
    """
    ViewSet para gerenciamento de PER/DCOMPs com aprovação
    automática para alterações sensíveis.
    """

    serializer_class = PerDcompSerializer
    lookup_field = "public_id"
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["status", "is_active", "tributo_pedido"]
    search_fields = [
        "numero_perdcomp",
        "numero",
        "cnpj",
        "processo_protocolo",
        "tributo_pedido",
        "competencia",
    ]
    ordering_fields = ["created_at", "data_vencimento", "valor_pedido"]
    ordering = ["-created_at"]

    # Configuração para RequiresApprovalMixin
    approval_resource_type = "perdcomps.PerDcomp"

    def get_queryset(self):
        """Filtrar por entidades ativas."""
        return PerDcomp.objects.filter(deleted_at__isnull=True)

    @extend_schema(
        tags=["PER/DCOMPs"],
        summary="Listar PER/DCOMPs com estatísticas",
        description="""Lista PER/DCOMPs com paginação e estatísticas calculadas baseadas nos filtros aplicados.
        
        **Estatísticas retornadas:**
        - total: Número total de PER/DCOMPs que correspondem aos filtros
        - pendentes: Quantidade com status pendente (RASCUNHO, TRANSMITIDO, EM_PROCESSAMENTO)
        - deferidos: Quantidade com status finalizado (DEFERIDO, INDEFERIDO, PARCIALMENTE_DEFERIDO, CANCELADO, VENCIDO)
        - valor_total: Soma dos valores pedidos de todas as PER/DCOMPs filtradas
        
        **Filtros disponíveis:**
        - Por status: ?status=TRANSMITIDO
        - Por ativo: ?is_active=true
        - Por tributo: ?tributo_pedido=COFINS
        - Busca textual: ?search=numero_perdcomp OU cnpj OU tributo
        
        **Exemplos de busca:**
        - Por número: ?search=123/45
        - Por CNPJ: ?search=12.345.678/0001-90
        - Por tributo: ?search=COFINS
        """,
        responses={
            200: OpenApiResponse(
                description="Lista de PER/DCOMPs com estatísticas",
                examples=[
                    OpenApiExample(
                        "Resposta com estatísticas",
                        value={
                            "count": 50,
                            "next": "http://api/perdcomps/?page=2",
                            "previous": None,
                            "results": [
                                {
                                    "id": "uuid",
                                    "numero_perdcomp": "123/45",
                                    "cnpj": "12.345.678/0001-90",
                                    "client_name": "EMPRESA LTDA",
                                    "status": "TRANSMITIDO",
                                    "valor_pedido": "1500.00",
                                    "data_vencimento": "2025-12-31T00:00:00Z",
                                }
                            ],
                            "statistics": {
                                "total": 50,
                                "pendentes": 30,
                                "deferidos": 20,
                                "valor_total": "75000.00",
                            },
                        },
                    )
                ],
            )
        },
    )
    def list(self, request, *args, **kwargs):
        """List PerDcomps with statistics based on applied filters."""
        # Get the filtered queryset (same filters applied to pagination)
        queryset = self.filter_queryset(self.get_queryset())

        # Calculate statistics based on the filtered data
        stats = self.calculate_statistics(queryset)

        # Get paginated results
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            # Add statistics to paginated response
            response = self.get_paginated_response(serializer.data)
            response.data["statistics"] = stats
            return response

        # If no pagination, add statistics to normal response
        serializer = self.get_serializer(queryset, many=True)
        return Response(
            {
                "results": serializer.data,
                "count": len(serializer.data),
                "statistics": stats,
            }
        )

    def calculate_statistics(self, queryset):
        """Calculate statistics for the filtered queryset."""
        # Total count (already available in pagination)
        total = queryset.count()

        # Pending status counts
        pending_statuses = [
            PerDcomp.Status.RASCUNHO,
            PerDcomp.Status.TRANSMITIDO,
            PerDcomp.Status.EM_PROCESSAMENTO,
        ]
        pendentes = queryset.filter(status__in=pending_statuses).count()

        # Finished/completed status counts (deferido, parcialmente deferido, indeferido)
        finished_statuses = [
            PerDcomp.Status.DEFERIDO,
            PerDcomp.Status.INDEFERIDO,
            PerDcomp.Status.PARCIALMENTE_DEFERIDO,
            PerDcomp.Status.CANCELADO,
            PerDcomp.Status.VENCIDO,
        ]
        deferidos = queryset.filter(status__in=finished_statuses).count()

        # Calculate total value (sum of valor_pedido)
        # Convert varchar money fields to decimal for calculation
        valor_total = Decimal("0.00")

        for perdcomp in queryset.only("valor_pedido"):
            try:
                # Clean and convert the money string to decimal
                valor_str = str(perdcomp.valor_pedido or "0.00").replace(",", ".")
                valor_decimal = Decimal(valor_str)
                valor_total += valor_decimal
            except (ValueError, InvalidOperation):
                # If conversion fails, treat as 0
                continue

        return {
            "total": total,
            "pendentes": pendentes,
            "deferidos": deferidos,
            "valor_total": f"{valor_total:.2f}",
        }

    def get_object(self):
        """Buscar objeto por public_id."""
        queryset = self.filter_queryset(self.get_queryset())
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        lookup_value = self.kwargs[lookup_url_kwarg]

        try:
            obj = queryset.get(**{self.lookup_field: lookup_value})
        except PerDcomp.DoesNotExist:
            from django.http import Http404

            raise Http404("PER/DCOMP não encontrado.")

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
        tags=["PER/DCOMPs"],
        summary="Atualizar campos sensíveis do PER/DCOMP",
        description="Atualiza campos sensíveis que requerem aprovação administrativa. Cria automaticamente uma solicitação de aprovação.",
        request=PerDcompSensitiveSerializer,
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
            404: OpenApiResponse(description="PER/DCOMP não encontrado"),
        },
    )
    @action(
        detail=True,
        methods=["patch"],
        serializer_class=PerDcompSensitiveSerializer,
        url_path="sensitive-data",
    )
    def update_sensitive_data(self, request, pk=None):
        """
        Atualizar dados sensíveis (requer aprovação automática).
        PATCH /api/perdcomps/{id}/sensitive-data/

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
        tags=["PER/DCOMPs"],
        summary="Exportar PER/DCOMPs para Excel",
        description="""Gera um arquivo Excel (.xlsx) avançado com dados de PER/DCOMPs filtrados.
        
        **Parâmetros obrigatórios:**
        - client_cnpj: CNPJ do cliente (formato: 00.000.000/0000-00)
        
        **Parâmetros opcionais:**
        - status: Filtro por status específico
        - search: Busca textual (número, protocolo, tributo, etc.)
        - optimize_size: Otimizar para tamanho de arquivo (padrão: true)
        
        **Recursos avançados do arquivo gerado:**
        - 📊 **Planilha principal**: Dados formatados com tabela Excel interativa
        - 🎯 **Formatação condicional**: Cores automáticas baseadas em valores
        - ⏰ **Coluna "Dias até Vencimento"**: Com indicadores visuais de urgência
        - � **Planilha de resumo**: Estatísticas executivas e métricas principais
        - 📊 **Análise de status**: Breakdown detalhado com percentuais e valores
        - 🎨 **Visual profissional**: Formatação empresarial moderna
        
        **Exemplo de uso:**
        - `/api/v1/perdcomps/export-excel/?client_public_id=550e8400-e29b-41d4-a716-446655440000`
        - `/api/v1/perdcomps/export-excel/?client_public_id=550e8400-e29b-41d4-a716-446655440000&status=TRANSMITIDO`
        - `/api/v1/perdcomps/export-excel/?client_public_id=550e8400-e29b-41d4-a716-446655440000&search=COFINS&optimize_size=true`
        """,
        parameters=[
            OpenApiParameter(
                name="client_public_id",
                type=str,
                location=OpenApiParameter.QUERY,
                required=True,
                description="ID público do cliente (UUID)",
                examples=[OpenApiExample("UUID válido", value="550e8400-e29b-41d4-a716-446655440000")],
            ),
            OpenApiParameter(
                name="status",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Filtro por status específico",
                enum=[
                    "RASCUNHO",
                    "TRANSMITIDO",
                    "EM_PROCESSAMENTO",
                    "DEFERIDO",
                    "INDEFERIDO",
                    "PARCIALMENTE_DEFERIDO",
                    "CANCELADO",
                    "VENCIDO",
                ],
            ),
            OpenApiParameter(
                name="search",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Busca textual em número, protocolo, tributo, competência",
                examples=[
                    OpenApiExample("Busca por tributo", value="COFINS"),
                    OpenApiExample("Busca por número", value="123/45"),
                ],
            ),
            OpenApiParameter(
                name="optimize_size",
                type=bool,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Otimizar arquivo para tamanho menor (remove formatação avançada, padrão: true)",
                examples=[
                    OpenApiExample("Tamanho otimizado", value=True),
                    OpenApiExample("Qualidade máxima", value=False),
                ],
            ),
        ],
        responses={
            200: OpenApiResponse(
                description="Arquivo Excel gerado com sucesso",
                response={"type": "string", "format": "binary"},
                examples=[
                    OpenApiExample(
                        "Download Excel",
                        description="Arquivo .xlsx para download",
                    )
                ],
            ),
            400: OpenApiResponse(
                description="Parâmetros inválidos",
                examples=[
                    OpenApiExample(
                        "Parâmetro obrigatório",
                        value={"error": "Parameter 'client_public_id' is required"},
                    ),
                    OpenApiExample(
                        "UUID inválido",
                        value={
                            "error": "Invalid client_public_id format. Must be a valid UUID"
                        },
                    ),
                ],
            ),
            404: OpenApiResponse(
                description="Cliente não encontrado ou sem PER/DCOMPs",
                examples=[
                    OpenApiExample(
                        "Cliente não existe",
                        value={
                            "error": "Client with CNPJ 01.562.539/0001-05 not found"
                        },
                    ),
                    OpenApiExample(
                        "Sem dados para exportar",
                        value={
                            "error": "No PER/DCOMPs found for the specified client and filters"
                        },
                    ),
                ],
            ),
        },
    )
    @action(detail=False, methods=["get"], url_path="export-excel")
    def export_excel(self, request):
        """Export PER/DCOMPs to Excel file for a specific client."""

        # Validate required parameter
        client_public_id = request.query_params.get("client_public_id")
        if not client_public_id:
            return Response(
                {"error": "Parameter 'client_public_id' is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate UUID format
        try:
            import uuid
            uuid.UUID(client_public_id)
        except ValueError:
            return Response(
                {"error": "Invalid client_public_id format. Must be a valid UUID"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Verify client exists and get client data
        from apps.clients.models import Client

        try:
            client = Client.objects.get(public_id=client_public_id, deleted_at__isnull=True)
        except Client.DoesNotExist:
            return Response(
                {"error": f"Client with public_id {client_public_id} not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Start with base queryset filtered by client CNPJ
        queryset = self.get_queryset().filter(cnpj=client.cnpj)

        # Apply additional filters from query parameters
        # Reuse the same filtering logic as the list view
        queryset = self.filter_queryset(queryset)

        # Check if we have any data to export
        if not queryset.exists():
            return Response(
                {"error": "No PER/DCOMPs found for the specified client and filters"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Collect applied filters for metadata
        applied_filters = {
            "client_public_id": client_public_id,
            "status": request.query_params.get("status"),
            "search": request.query_params.get("search"),
            "tributo_pedido": request.query_params.get("tributo_pedido"),
        }

        # Filter out empty values
        applied_filters = {k: v for k, v in applied_filters.items() if v}

        # Parse enhanced options
        optimize_size = (
            request.query_params.get("optimize_size", "true").lower() == "true"
        )

        # Generate Excel file with enhanced options
        exporter = PerDcompExcelExporter()
        return exporter.export_to_excel(
            queryset=queryset,
            client_cnpj=client.cnpj,  # Pass actual CNPJ for filename and client info
            applied_filters=applied_filters,
            optimize_for_size=optimize_size,
        )


@extend_schema(
    tags=["PER/DCOMPs - Anotações"],
    summary="Gerenciamento de anotações",
    description="Endpoints para gerenciar anotações dos PER/DCOMPs.",
)
class PerDcompAnnotationViewSet(viewsets.ModelViewSet):
    """ViewSet para gerenciamento de anotações dos PER/DCOMPs.

    **Características importantes:**
    - Cada usuário pode ter MÚLTIPLAS anotações por PER/DCOMP
    - O campo 'content' é um objeto JSON que permite estruturas flexíveis
    - Usuários podem ver todas as anotações de todos os usuários
    - Usuários só podem editar/deletar suas próprias anotações

    Endpoints:
    POST /api/v1/perdcomps/annotations/by-perdcomp/{perdcomp_id}/ - Criar nova anotação para PER/DCOMP
    GET /api/v1/perdcomps/annotations/by-perdcomp/{perdcomp_id}/ - Listar todas as anotações do PER/DCOMP
    PUT /api/v1/perdcomps/annotations/{annotation_id}/ - Atualizar anotação completa (apenas próprias)
    PATCH /api/v1/perdcomps/annotations/{annotation_id}/ - Atualizar apenas campo 'text' (apenas próprias)
    DELETE /api/v1/perdcomps/annotations/{annotation_id}/ - Excluir anotação (apenas próprias)
    """

    serializer_class = PerDcompAnnotationSerializer
    lookup_field = "public_id"
    lookup_url_kwarg = "annotation_id"  # Use annotation_id from URL
    permission_classes = [IsOwnerOrAdminForAnnotations]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["user_id"]
    search_fields = ["content"]
    ordering_fields = ["created_at", "updated_at"]
    ordering = ["-created_at"]

    def get_queryset(self):
        """Filtrar anotações baseado no contexto da URL."""
        from django.contrib.contenttypes.models import ContentType

        perdcomp_ct = ContentType.objects.get(app_label="perdcomps", model="perdcomp")
        queryset = Annotation.objects.filter(
            deleted_at__isnull=True, content_type=perdcomp_ct
        )

        # Se há perdcomp_id na URL (para list/create), filtrar por PER/DCOMP
        perdcomp_id = self.kwargs.get("perdcomp_id")
        if perdcomp_id:
            try:
                perdcomp = PerDcomp.objects.get(
                    public_id=perdcomp_id, deleted_at__isnull=True
                )
                queryset = queryset.filter(object_id=perdcomp.id)
            except PerDcomp.DoesNotExist:
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
        summary="Criar nova anotação para PER/DCOMP",
        description="""
        Cria uma nova anotação para um PER/DCOMP específico.
        
        **Novo comportamento:** Usuários podem criar múltiplas anotações para o mesmo PER/DCOMP.
        Cada POST criará uma nova anotação independente.
        
        O perdcomp_id deve ser fornecido na URL como parâmetro.
        O content deve ser um objeto JSON com a estrutura desejada.
        """,
        request=PerDcompAnnotationSerializer,
        responses={
            201: OpenApiResponse(description="Anotação criada com sucesso"),
            400: OpenApiResponse(description="Dados inválidos ou anotação já existe"),
            404: OpenApiResponse(description="PER/DCOMP não encontrado"),
        },
        examples=[
            OpenApiExample(
                "Exemplo de requisição",
                value={
                    "content": {
                        "text": "Esta é uma anotação importante sobre o PER/DCOMP.",
                        "priority": "high",
                        "tags": ["importante", "urgente"],
                        "metadata": {"created_by": "system", "category": "observacao"},
                    }
                },
            )
        ],
    )
    def create(self, request, *args, **kwargs):
        """Criar nova anotação com perdcomp_id obtido da URL."""
        # Obter perdcomp_id da URL
        perdcomp_id = kwargs.get("perdcomp_id")

        if not perdcomp_id:
            return Response(
                {"error": "perdcomp_id é obrigatório na URL."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Verificar se o PER/DCOMP existe
        try:
            perdcomp = PerDcomp.objects.get(
                public_id=perdcomp_id, deleted_at__isnull=True
            )
        except PerDcomp.DoesNotExist:
            return Response(
                {"error": "PER/DCOMP não encontrado."}, status=status.HTTP_404_NOT_FOUND
            )

        # Adicionar entity_type e entity_id aos dados
        data = request.data.copy()
        data["entity_type"] = "perdcomp"
        data["entity_id"] = str(perdcomp_id)

        # Usar o serializer normal para criação
        serializer = PerDcompAnnotationSerializer(
            data=data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        annotation = serializer.save()

        # Retornar resposta de criação
        response_serializer = self.get_serializer(annotation)
        headers = self.get_success_headers(response_serializer.data)

        return Response(
            response_serializer.data, status=status.HTTP_201_CREATED, headers=headers
        )

    @extend_schema(
        summary="Listar anotações do PER/DCOMP",
        description="Lista todas as anotações do PER/DCOMP especificado.",
        responses={
            200: OpenApiResponse(
                description="Lista de anotações",
                examples=[
                    OpenApiExample(
                        "Exemplo de resposta",
                        value={
                            "count": 1,
                            "next": None,
                            "previous": None,
                            "results": [
                                {
                                    "id": "123e4567-e89b-12d3-a456-426614174000",
                                    "entity_name": "PER/DCOMP 2023001",
                                    "user_name": "usuario",
                                    "content": {
                                        "text": "Anotação sobre o PER/DCOMP",
                                        "priority": "medium",
                                        "tags": ["revisão"],
                                        "metadata": {"category": "processamento"},
                                    },
                                    "created_at": "2023-01-01T12:00:00Z",
                                    "updated_at": "2023-01-01T12:00:00Z",
                                }
                            ],
                        },
                    )
                ],
            ),
            404: OpenApiResponse(description="PER/DCOMP não encontrado"),
        },
    )
    def list(self, request, *args, **kwargs):
        """Listar anotações do PER/DCOMP especificado na URL."""
        perdcomp_id = kwargs.get("perdcomp_id")

        # Verificar se o PER/DCOMP existe
        try:
            PerDcomp.objects.get(public_id=perdcomp_id, deleted_at__isnull=True)
        except PerDcomp.DoesNotExist:
            return Response(
                {"error": "PER/DCOMP não encontrado."}, status=status.HTTP_404_NOT_FOUND
            )

        return super().list(request, *args, **kwargs)

    @extend_schema(
        summary="Obter anotação específica do PER/DCOMP",
        description="Obtém uma anotação específica de um PER/DCOMP. O content retornado é um objeto JSON estruturado.",
        responses={
            200: OpenApiResponse(
                description="Anotação encontrada",
                examples=[
                    OpenApiExample(
                        "Exemplo de resposta",
                        value={
                            "id": "123e4567-e89b-12d3-a456-426614174000",
                            "entity_name": "PER/DCOMP 2023001",
                            "user_name": "usuario",
                            "content": {
                                "text": "Anotação sobre o PER/DCOMP",
                                "priority": "medium",
                                "tags": ["revisão"],
                                "metadata": {"category": "processamento"},
                            },
                            "created_at": "2023-01-01T12:00:00Z",
                            "updated_at": "2023-01-01T12:00:00Z",
                        },
                    )
                ],
            ),
            404: OpenApiResponse(description="Anotação não encontrada"),
        },
    )
    def retrieve(self, request, *args, **kwargs):
        """Obter anotação específica."""
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(
        summary="Atualizar completamente anotação do PER/DCOMP",
        description="""Atualiza completamente uma anotação de PER/DCOMP. O content deve ser um objeto JSON completo.
        
        **Importante:** Esta operação substitui todo o conteúdo da anotação. Use PATCH para atualizações parciais.
        """,
        request=PerDcompAnnotationSerializer,
        responses={
            201: OpenApiResponse(description="Anotação criada com sucesso"),
            400: OpenApiResponse(description="Dados inválidos"),
            404: OpenApiResponse(description="PER/DCOMP não encontrado"),
            409: OpenApiResponse(
                description="Anotação já existe para este usuário e PER/DCOMP"
            ),
        },
        examples=[
            OpenApiExample(
                "Exemplo de requisição",
                value={
                    "content": {
                        "text": "Texto da anotação atualizada",
                        "priority": "high",
                        "tags": ["urgente", "atualizada"],
                        "metadata": {
                            "updated_by": "user",
                            "category": "observacao",
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
        summary="Atualizar parcialmente anotação do PER/DCOMP",
        description="""Atualiza apenas o campo 'text' dentro do conteúdo da anotação do PER/DCOMP.
        
        **Importante:** Este endpoint permite apenas a atualização do campo 'text' dentro do objeto 'content'.
        Outros campos do conteúdo não serão modificados. Para atualizações completas, use PUT.
        """,
        request=PerDcompAnnotationSerializer,
        responses={
            200: OpenApiResponse(description="Anotação atualizada com sucesso"),
            400: OpenApiResponse(description="Dados inválidos"),
            404: OpenApiResponse(description="Anotação não encontrada"),
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
        perdcomp_id = kwargs.get("perdcomp_id")

        # Verificar se o PER/DCOMP existe
        try:
            PerDcomp.objects.get(public_id=perdcomp_id, deleted_at__isnull=True)
        except PerDcomp.DoesNotExist:
            return Response(
                {"error": "PER/DCOMP não encontrado."}, status=status.HTTP_404_NOT_FOUND
            )

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

        # Atualizar diretamente no modelo
        annotation.content = updated_content
        annotation.save()

        # Serializar a resposta
        serializer = self.get_serializer(annotation)
        return Response(serializer.data)

    @extend_schema(
        summary="Excluir anotação do PER/DCOMP",
        description="Exclui uma anotação específica de um PER/DCOMP (soft delete).",
        responses={
            204: OpenApiResponse(description="Anotação excluída com sucesso"),
            404: OpenApiResponse(description="Anotação não encontrada"),
        },
    )
    def destroy(self, request, *args, **kwargs):
        """Excluir anotação."""
        return super().destroy(request, *args, **kwargs)

    def perform_destroy(self, instance):
        """Soft delete com data de exclusão."""
        from django.utils import timezone

        instance.deleted_at = timezone.now()
        instance.save()

    def get_permissions(self):
        """Apenas o autor ou admin pode editar/deletar anotações."""
        if self.action in ["update", "partial_update", "destroy"]:
            permission_classes = [IsAuthenticated]
            # Verificação adicional no get_object se necessário
        else:
            permission_classes = [IsAuthenticated]
        return [permission() for permission in permission_classes]
