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
from common.shared.permissions import (
    IsOwnerOrAdminForAnnotations,
    IsOwnerOrAdminForAttachedFiles,
)
from .models import PerDcomp
from common.shared.models import Annotation, AttachedFile
from .serializers import (
    PerDcompSerializer,
    PerDcompBasicSerializer,
    PerDcompSensitiveSerializer,
    PerDcompAttachedFileSerializer,
    PerDcompAnnotationSerializer,
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
    search_fields = ["numero_perdcomp", "numero", "cnpj", "processo_protocolo"]
    ordering_fields = ["created_at", "data_vencimento", "valor_pedido"]
    ordering = ["-created_at"]

    # Configuração para RequiresApprovalMixin
    approval_resource_type = "perdcomps.PerDcomp"

    def get_queryset(self):
        """Filtrar por entidades ativas."""
        return PerDcomp.objects.filter(deleted_at__isnull=True)

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
    tags=["PER/DCOMPs - Arquivos"],
    summary="Gerenciamento de arquivos anexados",
    description="Endpoints para gerenciar arquivos anexados aos PER/DCOMPs.",
)
class PerDcompAttachedFileViewSet(viewsets.ModelViewSet):
    """ViewSet para gerenciamento de arquivos anexados aos PER/DCOMPs."""

    serializer_class = PerDcompAttachedFileSerializer
    lookup_field = "public_id"
    permission_classes = [IsOwnerOrAdminForAttachedFiles]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ["file_type", "mime_type"]
    ordering_fields = ["created_at", "file_size"]
    ordering = ["-created_at"]

    def get_queryset(self):
        """Filtrar por arquivos não deletados do usuário (ou todos se admin)."""
        from django.contrib.contenttypes.models import ContentType

        perdcomp_ct = ContentType.objects.get(app_label="perdcomps", model="perdcomp")
        queryset = AttachedFile.objects.filter(
            deleted_at__isnull=True, content_type=perdcomp_ct
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

    def perform_destroy(self, instance):
        """Soft delete com data de exclusão."""
        from django.utils import timezone

        instance.deleted_at = timezone.now()
        instance.save()


@extend_schema(
    tags=["PER/DCOMPs - Anotações"],
    summary="Gerenciamento de anotações",
    description="Endpoints para gerenciar anotações dos PER/DCOMPs.",
)
class PerDcompAnnotationViewSet(viewsets.ModelViewSet):
    """ViewSet para gerenciamento de anotações dos PER/DCOMPs.

    Endpoints:
    POST /api/v1/perdcomps/annotations/{perdcomp_id}/ - Criar anotação para PER/DCOMP
    GET /api/v1/perdcomps/annotations/{perdcomp_id}/ - Listar anotações do PER/DCOMP
    PUT /api/v1/perdcomps/annotations/{annotation_id}/ - Atualizar anotação completa
    PATCH /api/v1/perdcomps/annotations/{annotation_id}/ - Atualizar apenas campo 'text'
    DELETE /api/v1/perdcomps/annotations/{annotation_id}/ - Excluir anotação
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
        summary="Criar ou atualizar anotação para PER/DCOMP",
        description="""
        Cria uma nova anotação para um PER/DCOMP específico ou atualiza a anotação existente.
        
        **Importante:** Cada usuário pode ter apenas UMA anotação por PER/DCOMP.
        Se uma anotação já existir para este usuário e PER/DCOMP, ela será atualizada.
        
        O perdcomp_id deve ser fornecido na URL como parâmetro.
        O content deve ser um objeto JSON com a estrutura desejada.
        """,
        request=PerDcompAnnotationSerializer,
        responses={
            201: OpenApiResponse(description="Anotação criada com sucesso"),
            200: OpenApiResponse(description="Anotação atualizada com sucesso"),
            400: OpenApiResponse(description="Dados inválidos"),
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
        """Criar ou atualizar anotação com perdcomp_id obtido da URL."""
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

        # Usar o serializer que tem a lógica de upsert
        serializer = PerDcompAnnotationSerializer(
            data=data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)

        # Verificar se já existe anotação para este usuário e PER/DCOMP
        user_id = request.user.id
        existing_annotation = Annotation.objects.filter(
            user_id=user_id,
            content_type__app_label="perdcomps",
            content_type__model="perdcomp",
            object_id=perdcomp.id,
            deleted_at__isnull=True,
        ).first()

        is_update = existing_annotation is not None
        annotation = (
            serializer.save()
        )  # Aqui o serializer faz create ou update automaticamente

        # Retornar resposta com status apropriado
        response_serializer = self.get_serializer(annotation)
        headers = self.get_success_headers(response_serializer.data)

        status_code = status.HTTP_200_OK if is_update else status.HTTP_201_CREATED

        return Response(response_serializer.data, status=status_code, headers=headers)

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
            200: OpenApiResponse(description="Anotação atualizada com sucesso"),
            400: OpenApiResponse(description="Dados inválidos"),
            404: OpenApiResponse(description="Anotação não encontrada"),
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

        return super().update(request, *args, **kwargs)

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

        # Preparar dados para serializer com content completo
        data = {"content": updated_content}

        serializer = self.get_serializer(annotation, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

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
