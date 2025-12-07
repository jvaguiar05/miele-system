import logging
from rest_framework import viewsets, status, parsers
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from django.http import FileResponse
from django.db import transaction
from drf_spectacular.utils import extend_schema, OpenApiExample, OpenApiParameter

from .models import AttachedFile
from .serializers import (
    AttachedFileListSerializer,
    AttachedFileCreateSerializer,
    AttachedFileUpdateSerializer,
)
from common.services.google_drive import drive_service
from .utils import resolve_entity

logger = logging.getLogger(__name__)


@extend_schema(
    tags=["Google Drive Integration - Proxy"],
    summary="Gerenciamento de Arquivos Anexados",
    description="""
    Endpoints para upload, listagem, download e exclusão de arquivos anexados a Clientes ou PerDcomps.
    Toda a transferência de arquivos é feita via Proxy pelo Backend.
    """,
)
class AttachedFileViewSet(viewsets.ModelViewSet):
    queryset = AttachedFile.objects.all()
    lookup_field = "public_id"
    lookup_url_kwarg = "public_id"
    parser_classes = [parsers.MultiPartParser, parsers.FormParser]
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == "create":
            return AttachedFileCreateSerializer
        if self.action in ["update", "partial_update"]:
            return AttachedFileUpdateSerializer
        return AttachedFileListSerializer

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="object_id",
                description="UUID da entidade (Cliente ou PerDcomp) para filtrar os arquivos.",
                required=True,
                type=str,
            )
        ]
    )
    def list(self, request, *args, **kwargs):
        """
        Lista arquivos de uma entidade específica.
        Requer query param: ?object_id={uuid}
        """
        object_id = request.query_params.get("object_id")

        if not object_id:
            return Response(
                {"error": "Parâmetro 'object_id' é obrigatório para listagem."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Resolver a entidade para pegar o ID numérico interno
        entity, entity_type = resolve_entity(object_id)

        if not entity:
            return Response(
                {"error": "Entidade não encontrada."}, status=status.HTTP_404_NOT_FOUND
            )

        # Filtra os arquivos daquela entidade
        files = AttachedFile.objects.filter(
            object_id=entity.id,
            content_type__model=entity_type,
        )

        serializer = self.get_serializer(files, many=True)
        return Response(serializer.data)

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        file_obj = serializer.validated_data["file"]
        object_uuid = serializer.validated_data["object_id"]
        file_type = serializer.validated_data["file_type"]
        description = serializer.validated_data.get("description", "")

        # Tenta pegar o tipo resolvido pelo serializer para evitar consulta dupla
        entity_type = serializer.validated_data.get("resolved_entity_type")

        # Se por algum motivo o serializer não injetou, resolvemos manualmente
        entity = None
        if not entity_type:
            entity, entity_type = resolve_entity(object_uuid)
            if not entity:
                return Response({"error": "Entidade não encontrada."}, status=404)
        else:
            # Se já temos o tipo, precisamos da instância para salvar no banco
            # (Otimização: em projetos grandes, poderíamos usar apenas o ID se não precisássemos da instância object)
            entity, _ = resolve_entity(object_uuid)

        logger.info(f"Iniciando upload proxy para {entity_type} {object_uuid}")

        # Extrair MIME Type real do arquivo (Ex: 'application/pdf')
        # Django In-Memory files possuem esse atributo automaticamente
        mime_type = getattr(file_obj, "content_type", "application/octet-stream")

        try:
            # 1. Upload para Drive (Proxy)
            drive_id = drive_service.upload_stream(
                file_obj,
                filename=file_obj.name,
                entity_type=entity_type,
                mime_type=mime_type,
            )

            # 2. Salvar no Banco
            attached_file = AttachedFile.objects.create(
                content_object=entity,
                uploaded_by_id=request.user.id,
                file_name=file_obj.name,
                file_size=file_obj.size,
                file_type=file_type,
                mime_type=mime_type,  # Salvando para usar no download
                drive_file_id=drive_id,
                description=description,
            )

            response_serializer = AttachedFileListSerializer(attached_file)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"Erro crítico no upload: {e}")
            # Rollback automático do banco via transaction.atomic
            return Response(
                {"error": "Falha na comunicação com o Google Drive."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

    @action(detail=True, methods=["get"])
    def download(self, request, public_id=None):
        """
        Proxy de Download: Drive -> Backend RAM -> Usuário
        """
        instance = self.get_object()

        try:
            # Baixa do Drive para memória
            file_stream = drive_service.download_stream(instance.drive_file_id)

            # Retorna stream para o navegador com o Content-Type correto
            response = FileResponse(
                file_stream,
                as_attachment=True,
                filename=instance.file_name,
                content_type=instance.mime_type,
            )
            return response

        except Exception as e:
            logger.error(f"Erro ao baixar arquivo {public_id}: {e}")
            return Response(
                {"error": "Arquivo indisponível no provedor de nuvem."},
                status=status.HTTP_404_NOT_FOUND,
            )

    def perform_destroy(self, instance):
        """
        Remove do Drive e depois do Banco.
        """
        try:
            drive_service.delete_file(instance.drive_file_id)
        except Exception as e:
            # Se já não existe no Drive (404), loga aviso mas permite deletar do banco
            logger.warning(
                f"Erro ao deletar do Drive (ignorando para limpar banco): {e}"
            )

        instance.delete()
