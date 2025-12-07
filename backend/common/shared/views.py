import logging
from rest_framework import viewsets, status, parsers
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from django.http import FileResponse
from django.db import transaction
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes

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
    summary="Gerenciamento de Arquivos",
    description="""
    API para gerenciamento centralizado de arquivos anexados a entidades (Clientes e PER/DCOMPs).
    
    **Arquitetura Proxy:**
    - O Frontend envia/recebe o arquivo através desta API.
    - Esta API valida regras de negócio e faz o streaming para o Google Drive (OAuth 2.0).
    - Nenhum link direto do Google é exposto ao usuário final.
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
        summary="Listar arquivos de uma entidade",
        description="Retorna a lista de todos os arquivos anexados a um Cliente ou PER/DCOMP específico.",
        parameters=[
            OpenApiParameter(
                name="object_id",
                description="UUID da entidade (Cliente ou PerDcomp) para filtrar os arquivos.",
                required=True,
                type=OpenApiTypes.UUID,
                location=OpenApiParameter.QUERY,
            )
        ],
        responses={
            200: AttachedFileListSerializer(many=True),
            400: OpenApiTypes.OBJECT,
            404: OpenApiTypes.OBJECT,
        },
    )
    def list(self, request, *args, **kwargs):
        object_id = request.query_params.get("object_id")

        if not object_id:
            return Response(
                {
                    "error": "Parâmetro 'object_id' (UUID) é obrigatório na query string."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        entity, entity_type = resolve_entity(object_id)

        if not entity:
            return Response(
                {"error": "Entidade não encontrada com o UUID fornecido."},
                status=status.HTTP_404_NOT_FOUND,
            )

        files = AttachedFile.objects.filter(
            object_id=entity.id,
            content_type__model=entity_type,
        )

        serializer = self.get_serializer(files, many=True)
        return Response(serializer.data)

    @extend_schema(
        summary="Fazer upload de um novo arquivo",
        description="""
        Recebe um arquivo binário e seus metadados via `multipart/form-data`.
        Realiza upload síncrono para o Google Drive e salva referência no banco.
        """,
        request={"multipart/form-data": AttachedFileCreateSerializer},
        responses={
            201: AttachedFileListSerializer,
            400: OpenApiTypes.OBJECT,
            404: OpenApiTypes.OBJECT,
            502: OpenApiTypes.OBJECT,
        },
    )
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        file_obj = serializer.validated_data["file"]
        object_uuid = serializer.validated_data["object_id"]
        file_type = serializer.validated_data["file_type"]
        description = serializer.validated_data.get("description", "")
        metadata = serializer.validated_data.get("metadata", {})

        # Tenta pegar o tipo resolvido pelo serializer
        entity_type = serializer.validated_data.get("resolved_entity_type")

        # Fallback de segurança
        entity = None
        if not entity_type:
            entity, entity_type = resolve_entity(object_uuid)
            if not entity:
                return Response({"error": "Entidade não encontrada."}, status=404)
        else:
            entity, _ = resolve_entity(object_uuid)

        logger.info(f"Iniciando upload proxy para {entity_type} {object_uuid}")

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
                mime_type=mime_type,
                drive_file_id=drive_id,
                description=description,
                metadata=metadata,
            )

            response_serializer = AttachedFileListSerializer(attached_file)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"Erro crítico no upload: {e}")
            return Response(
                {
                    "error": "Falha na comunicação com o provedor de armazenamento (Google Drive)."
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

    @extend_schema(
        summary="Atualizar arquivo ou metadados",
        description="""
        Permite atualizar a descrição, renomear o arquivo ou **substituir o arquivo físico**.
        
        - Se enviar `file_name`: Renomeia no banco e no Drive.
        - Se enviar `file`: Substitui o conteúdo no Drive e atualiza tamanho/mime_type no banco.
        - Se enviar `description`: Atualiza apenas no banco.
        """,
        request={"multipart/form-data": AttachedFileUpdateSerializer},
        responses={200: AttachedFileListSerializer},
    )
    @transaction.atomic
    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        # Dados recebidos
        new_file = serializer.validated_data.get("file")
        new_name = serializer.validated_data.get("file_name")
        description = serializer.validated_data.get("description")

        updates_made = False

        try:
            # Se tiver novo arquivo ou novo nome, precisamos chamar o Drive
            if new_file or new_name:
                mime_type = (
                    getattr(new_file, "content_type", None) if new_file else None
                )

                # Chamada ao Service (Atualiza no Google)
                drive_service.update_file(
                    file_id=instance.drive_file_id,
                    file_obj=new_file,
                    new_name=new_name,
                    mime_type=mime_type,
                )

                # Atualiza campos técnicos no Banco se mudou o arquivo
                if new_file:
                    instance.file_size = new_file.size
                    instance.mime_type = mime_type
                    # Opcional: Atualizar quem modificou (uploaded_by) para o usuário atual?
                    # instance.uploaded_by_id = request.user.id

                updates_made = True

            # Atualiza campos simples no Banco
            if new_name:
                instance.file_name = new_name
                updates_made = True

            if description is not None:
                instance.description = description
                updates_made = True

            if updates_made:
                instance.save()

            return Response(AttachedFileListSerializer(instance).data)

        except Exception as e:
            logger.error(f"Erro ao atualizar arquivo {instance.public_id}: {e}")
            return Response(
                {"error": "Falha ao atualizar arquivo no provedor de armazenamento."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

    @extend_schema(exclude=True)
    def update(self, request, *args, **kwargs):
        # Redireciona PUT para PATCH para garantir lógica unificada
        return self.partial_update(request, *args, **kwargs)

    @extend_schema(
        summary="Baixar arquivo (Download Proxy)",
        description="""
        Faz o streaming do arquivo diretamente do Google Drive para o navegador do usuário.
        Retorna o arquivo com o `Content-Type` original.
        """,
        responses={
            200: {
                "description": "Arquivo binário",
                "content": {"*/*": {"schema": {"type": "string", "format": "binary"}}},
            },
            404: OpenApiTypes.OBJECT,
        },
    )
    @action(detail=True, methods=["get"])
    def download(self, request, public_id=None):
        instance = self.get_object()

        try:
            file_stream = drive_service.download_stream(instance.drive_file_id)

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
                {"error": "Arquivo indisponível ou corrompido no provedor de nuvem."},
                status=status.HTTP_404_NOT_FOUND,
            )

    @extend_schema(
        summary="Visualizar arquivo (Inline Preview)",
        description="""
        Semelhante ao download, mas instrui o navegador a tentar renderizar o arquivo 
        na própria aba (ex: abrir PDF, exibir Imagem) em vez de forçar o 'Salvar como'.
        """,
        responses={
            200: {
                "description": "Arquivo binário",
                "content": {"*/*": {"schema": {"type": "string", "format": "binary"}}},
            },
            404: OpenApiTypes.OBJECT,
        },
    )
    @action(detail=True, methods=["get"])
    def preview(self, request, public_id=None):
        instance = self.get_object()

        try:
            file_stream = drive_service.download_stream(instance.drive_file_id)

            response = FileResponse(
                file_stream,
                as_attachment=False,  # Inline display
                filename=instance.file_name,
                content_type=instance.mime_type,
            )
            return response

        except Exception as e:
            logger.error(f"Erro ao gerar preview do arquivo {public_id}: {e}")
            return Response(
                {"error": "Arquivo indisponível para visualização."},
                status=status.HTTP_404_NOT_FOUND,
            )

    @extend_schema(
        summary="Remover arquivo permanentemente",
        description="""
        Remove o registro do banco de dados E apaga o arquivo físico no Google Drive.
        Esta ação é irreversível.
        """,
        responses={
            204: None,
            404: OpenApiTypes.OBJECT,
        },
    )
    def destroy(self, request, *args, **kwargs):
        # A lógica de deleção física foi movida para signals.py para garantir consistência
        # Aqui apenas chamamos o delete padrão do DRF, que aciona o signal.
        return super().destroy(request, *args, **kwargs)
