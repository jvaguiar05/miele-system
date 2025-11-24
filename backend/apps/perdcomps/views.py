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
    GET /api/v1/perdcomps/annotations/{perdcomp_id}/{annotation_id}/ - Obter anotação específica
    PUT/PATCH /api/v1/perdcomps/annotations/{perdcomp_id}/{annotation_id}/ - Atualizar anotação
    DELETE /api/v1/perdcomps/annotations/{perdcomp_id}/{annotation_id}/ - Excluir anotação
    """

    serializer_class = PerDcompAnnotationSerializer
    lookup_field = "public_id"
    lookup_url_kwarg = "annotation_id"  # Use annotation_id from URL
    permission_classes = [IsOwnerOrAdminForAnnotations]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ["content"]
    ordering_fields = ["created_at", "updated_at"]
    ordering = ["-created_at"]

    def get_queryset(self):
        """Filtrar anotações do PER/DCOMP especificado na URL."""
        from django.contrib.contenttypes.models import ContentType

        perdcomp_ct = ContentType.objects.get(app_label="perdcomps", model="perdcomp")
        queryset = Annotation.objects.filter(
            deleted_at__isnull=True, content_type=perdcomp_ct
        )

        # Filtrar pelo perdcomp_id da URL se fornecido
        perdcomp_id = self.kwargs.get("perdcomp_id")
        if perdcomp_id:
            # Verificar se o PER/DCOMP existe
            try:
                perdcomp = PerDcomp.objects.get(
                    public_id=perdcomp_id, deleted_at__isnull=True
                )
                # Filtrar anotações deste PER/DCOMP específico
                queryset = queryset.filter(object_id=perdcomp.id)
            except PerDcomp.DoesNotExist:
                # Se PER/DCOMP não existe, retornar queryset vazio
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
        summary="Criar anotação para PER/DCOMP",
        description="""
        Cria uma nova anotação para um PER/DCOMP específico.
        
        O perdcomp_id deve ser fornecido na URL como parâmetro.
        """,
        request=PerDcompAnnotationSerializer,
        responses={
            201: OpenApiResponse(description="Anotação criada com sucesso"),
            400: OpenApiResponse(description="Dados inválidos"),
            404: OpenApiResponse(description="PER/DCOMP não encontrado"),
        },
        examples=[
            OpenApiExample(
                "Exemplo de requisição",
                value={"content": "Esta é uma anotação importante sobre o PER/DCOMP."},
            )
        ],
    )
    def create(self, request, *args, **kwargs):
        """Criar anotação com perdcomp_id obtido da URL."""
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

        # Serializar dados do request
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Adicionar entity_type e entity_id manualmente
        validated_data = serializer.validated_data
        validated_data["entity_type"] = "perdcomp"
        validated_data["entity_id"] = str(perdcomp_id)  # Usar o UUID do PER/DCOMP

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
        summary="Listar anotações do PER/DCOMP",
        description="Lista todas as anotações do PER/DCOMP especificado.",
        responses={
            200: OpenApiResponse(description="Lista de anotações"),
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
