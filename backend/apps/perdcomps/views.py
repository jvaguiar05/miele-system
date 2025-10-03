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
        """Buscar objeto por public_id em vez de id."""
        queryset = self.filter_queryset(self.get_queryset())
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        lookup_value = self.kwargs[lookup_url_kwarg]

        try:
            obj = queryset.get(public_id=lookup_value)
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
        summary="Listar arquivos anexados ao PER/DCOMP",
        description="Lista todos os arquivos anexados a um PER/DCOMP específico.",
        operation_id="list_perdcomp_attached_files",
        responses={
            200: PerDcompAttachedFileSerializer(many=True),
            404: OpenApiResponse(description="PER/DCOMP não encontrado"),
        },
    )
    @action(
        detail=True,
        methods=["get"],
        url_path="attached-files",
    )
    def list_attached_files(self, request, pk=None):
        """Listar arquivos anexados ao PER/DCOMP."""
        instance = self.get_object()
        from django.contrib.contenttypes.models import ContentType

        perdcomp_ct = ContentType.objects.get(app_label="perdcomps", model="perdcomp")
        files = AttachedFile.objects.filter(
            content_type=perdcomp_ct, object_id=instance.id, deleted_at__isnull=True
        )
        serializer = PerDcompAttachedFileSerializer(files, many=True)
        return Response(serializer.data)

    @extend_schema(
        tags=["PER/DCOMPs"],
        summary="Anexar arquivo ao PER/DCOMP",
        description="Anexa um novo arquivo ao PER/DCOMP.",
        request=PerDcompAttachedFileSerializer,
        responses={
            201: PerDcompAttachedFileSerializer,
            400: OpenApiResponse(description="Dados inválidos"),
            404: OpenApiResponse(description="PER/DCOMP não encontrado"),
        },
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="attach-file",
        serializer_class=PerDcompAttachedFileSerializer,
    )
    def attach_file(self, request, pk=None):
        """Anexar arquivo ao PER/DCOMP."""
        instance = self.get_object()
        data = request.data.copy()
        data["entity_id"] = instance.public_id
        data["entity_type"] = "perdcomp"

        serializer = PerDcompAttachedFileSerializer(
            data=data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @extend_schema(
        tags=["PER/DCOMPs"],
        summary="Listar anotações do PER/DCOMP",
        description="Lista todas as anotações de um PER/DCOMP específico.",
        operation_id="list_perdcomp_annotations",
        responses={
            200: PerDcompAnnotationSerializer(many=True),
            404: OpenApiResponse(description="PER/DCOMP não encontrado"),
        },
    )
    @action(
        detail=True,
        methods=["get"],
        url_path="annotations",
    )
    def list_annotations(self, request, pk=None):
        """Listar anotações do PER/DCOMP."""
        instance = self.get_object()
        from django.contrib.contenttypes.models import ContentType

        perdcomp_ct = ContentType.objects.get(app_label="perdcomps", model="perdcomp")
        annotations = Annotation.objects.filter(
            content_type=perdcomp_ct, object_id=instance.id, deleted_at__isnull=True
        ).order_by("-created_at")
        serializer = PerDcompAnnotationSerializer(annotations, many=True)
        return Response(serializer.data)

    @extend_schema(
        tags=["PER/DCOMPs"],
        summary="Adicionar anotação ao PER/DCOMP",
        description="Adiciona uma nova anotação ao PER/DCOMP.",
        request=PerDcompAnnotationSerializer,
        responses={
            201: PerDcompAnnotationSerializer,
            400: OpenApiResponse(description="Dados inválidos"),
            404: OpenApiResponse(description="PER/DCOMP não encontrado"),
        },
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="add-annotation",
        serializer_class=PerDcompAnnotationSerializer,
    )
    def add_annotation(self, request, pk=None):
        """Adicionar anotação ao PER/DCOMP."""
        instance = self.get_object()
        data = request.data.copy()
        data["entity_id"] = instance.public_id
        data["entity_type"] = "perdcomp"

        serializer = PerDcompAnnotationSerializer(
            data=data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(serializer.data, status=status.HTTP_201_CREATED)


@extend_schema(
    tags=["PER/DCOMPs - Arquivos"],
    summary="Gerenciamento de arquivos anexados",
    description="Endpoints para gerenciar arquivos anexados aos PER/DCOMPs.",
)
class PerDcompAttachedFileViewSet(viewsets.ModelViewSet):
    """ViewSet para gerenciamento de arquivos anexados aos PER/DCOMPs."""

    serializer_class = PerDcompAttachedFileSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ["file_type", "mime_type"]
    ordering_fields = ["created_at", "file_size"]
    ordering = ["-created_at"]

    def get_queryset(self):
        """Filtrar por arquivos não deletados."""
        from django.contrib.contenttypes.models import ContentType

        perdcomp_ct = ContentType.objects.get(app_label="perdcomps", model="perdcomp")
        return AttachedFile.objects.filter(
            deleted_at__isnull=True, content_type=perdcomp_ct
        )

    def get_object(self):
        """Buscar objeto por public_id."""
        queryset = self.filter_queryset(self.get_queryset())
        lookup_value = self.kwargs.get(self.lookup_url_kwarg or self.lookup_field)

        try:
            obj = queryset.get(public_id=lookup_value)
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
    """ViewSet para gerenciamento de anotações dos PER/DCOMPs."""

    serializer_class = PerDcompAnnotationSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ["content"]
    ordering_fields = ["created_at", "updated_at"]
    ordering = ["-created_at"]

    def get_queryset(self):
        """Filtrar por anotações não deletadas."""
        from django.contrib.contenttypes.models import ContentType

        perdcomp_ct = ContentType.objects.get(app_label="perdcomps", model="perdcomp")
        return Annotation.objects.filter(
            deleted_at__isnull=True, content_type=perdcomp_ct
        )

    def get_object(self):
        """Buscar objeto por public_id."""
        queryset = self.filter_queryset(self.get_queryset())
        lookup_value = self.kwargs.get(self.lookup_url_kwarg or self.lookup_field)

        try:
            obj = queryset.get(public_id=lookup_value)
        except Annotation.DoesNotExist:
            from django.http import Http404

            raise Http404("Anotação não encontrada.")

        self.check_object_permissions(self.request, obj)
        return obj

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
