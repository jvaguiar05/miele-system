"""
ViewSets genéricos para módulos compartilhados.
"""

import logging
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from drf_spectacular.openapi import OpenApiTypes
from django.http import Http404

from .models import AttachedFile
from .serializers import (
    AttachedFileListSerializer,
    AttachedFileDetailSerializer,
    AttachedFileCreateSerializer,
    AttachedFileUpdateSerializer,
)
from .services import AttachedFileService
from .permissions import IsOwnerOrAdminForAttachedFiles

logger = logging.getLogger(__name__)


@extend_schema(tags=["Google Drive - Arquivos"])
class AttachedFileViewSet(viewsets.ModelViewSet):
    """
    ViewSet genérico para gestão de arquivos anexados.

    **Funcionalidades:**
    - Listar arquivos por entidade (Cliente ou PER/DCOMP)
    - Criar novos arquivos anexados
    - Atualizar informações de arquivos
    - Excluir arquivos (apenas se removidos do Google Drive)

    **Validações:**
    - POST/PUT: Arquivo DEVE existir no Google Drive
    - DELETE: Arquivo NÃO DEVE existir no Google Drive
    - Ownership: Usuário deve ter permissão sobre a entidade
    """

    queryset = AttachedFile.objects.all()
    permission_classes = [IsAuthenticated, IsOwnerOrAdminForAttachedFiles]
    lookup_field = "public_id"
    lookup_url_kwarg = "public_id"

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["file_type", "sync_status"]
    search_fields = ["file_name", "description"]
    ordering_fields = ["created_at", "file_name", "file_size"]
    ordering = ["-created_at"]

    def get_queryset(self):
        """Filtrar arquivos com base nos parâmetros da query."""
        queryset = super().get_queryset()

        # Filtrar por object_id se fornecido
        object_id = self.request.query_params.get("object_id")
        if object_id:
            try:
                entity_queryset = AttachedFileService.get_files_for_entity(object_id)
                return entity_queryset
            except Exception as e:
                logger.error(f"Erro ao filtrar por object_id {object_id}: {e}")
                return queryset.none()

        # Se não há object_id, retornar apenas arquivos do usuário (se não for admin)
        if not self.request.user.is_staff:
            queryset = queryset.filter(uploaded_by_id=self.request.user.id)

        return queryset.select_related("content_type")

    def get_serializer_class(self):
        """Retorna serializer apropriado por ação."""
        if self.action == "list":
            return AttachedFileListSerializer
        elif self.action == "create":
            return AttachedFileCreateSerializer
        elif self.action in ["update", "partial_update"]:
            return AttachedFileUpdateSerializer
        return AttachedFileDetailSerializer

    @extend_schema(
        summary="Listar arquivos anexados",
        description="Lista arquivos anexados filtrados por entidade (Cliente ou PER/DCOMP)",
        parameters=[
            OpenApiParameter(
                "object_id",
                OpenApiTypes.UUID,
                location=OpenApiParameter.QUERY,
                required=True,
                description="Public ID da entidade (Cliente ou PER/DCOMP)",
            ),
            OpenApiParameter(
                "search",
                OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Buscar por nome ou descrição do arquivo",
            ),
            OpenApiParameter(
                "file_type",
                OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Filtrar por tipo de arquivo",
            ),
        ],
        examples=[
            OpenApiExample(
                "Arquivos de cliente",
                summary="Listar arquivos de um cliente",
                description="Exemplo de listagem de arquivos anexados a um cliente específico",
                value={
                    "count": 2,
                    "next": None,
                    "previous": None,
                    "results": [
                        {
                            "id": "123e4567-e89b-12d3-a456-426614174000",
                            "file_name": "Contrato_ABC_2024.pdf",
                            "file_type": "contrato",
                            "drive_file_id": "1FAKE_ID_FOR_TESTING_DELETE_123456789ABC",
                            "file_size": 1024000,
                            "file_size_human": "1.0 MB",
                            "entity_type": "client",
                            "entity_name": "Empresa ABC Ltda",
                            "uploaded_by_name": "joao.silva",
                            "sync_status": "synced",
                            "created_at": "2024-12-06T10:00:00Z",
                        }
                    ],
                },
            )
        ],
    )
    def list(self, request):
        """Listar arquivos por entidade."""
        object_id = request.query_params.get("object_id")
        if not object_id:
            return Response(
                {"error": "object_id é obrigatório para listar arquivos"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return super().list(request)

    @extend_schema(
        summary="Criar arquivo anexado",
        description="Cria novo arquivo anexado com validação de existência no Google Drive",
        examples=[
            OpenApiExample(
                "Criar arquivo de contrato",
                summary="Anexar contrato a cliente",
                description="Exemplo de criação de arquivo anexado",
                value={
                    "object_id": "123e4567-e89b-12d3-a456-426614174000",
                    "file_type": "contrato",
                    "file_name": "Contrato_ABC_2024.pdf",
                    "drive_file_id": "1AbCdEfGhIjKlMnOpQrStUvWxYz1234567890123",
                    "file_size": 1024000,
                    "description": "Contrato de prestação de serviços assinado em 2024",
                },
            )
        ],
    )
    def create(self, request):
        """Criar novo arquivo anexado."""
        try:
            return super().create(request)
        except ValidationError as e:
            logger.error(f"Erro de validação ao criar arquivo: {e}")

            # Tratar erros de validação específicos
            if hasattr(e, "detail") and isinstance(e.detail, dict):
                # Extrair mensagens limpas dos ErrorDetails
                clean_errors = {}
                for field, errors in e.detail.items():
                    if isinstance(errors, list) and len(errors) > 0:
                        error_msg = str(errors[0])
                        # Extrair mensagem do ErrorDetail se necessário
                        if "ErrorDetail" in error_msg and "string=" in error_msg:
                            import re

                            match = re.search(r"string='([^']*)'", error_msg)
                            if match:
                                error_msg = match.group(1)
                        clean_errors[field] = error_msg
                    else:
                        clean_errors[field] = str(errors)

                return Response(clean_errors, status=status.HTTP_400_BAD_REQUEST)

            # Para erros gerais (não por campo)
            error_message = str(e)
            if "ErrorDetail" in error_message and "string=" in error_message:
                import re

                match = re.search(r"string='([^']*)'", error_message)
                if match:
                    error_message = match.group(1)

            return Response(
                {"error": error_message},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.error(f"Erro ao criar arquivo anexado: {e}")

            # Verificar se é erro de entidade não encontrada
            if "não encontrado" in str(e).lower():
                return Response(
                    {"error": "Entidade não encontrada para o object_id fornecido"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            return Response(
                {"error": "Erro interno ao processar arquivo"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        summary="Atualizar arquivo anexado",
        description="Atualiza informações do arquivo com validação do Google Drive",
        examples=[
            OpenApiExample(
                "Atualizar arquivo",
                summary="Atualizar dados do arquivo",
                description="Exemplo de atualização de arquivo anexado",
                value={
                    "file_type": "contrato",
                    "file_name": "Contrato_ABC_2024_Revisado.pdf",
                    "drive_file_id": "1AbCdEfGhIjKlMnOpQrStUvWxYz1234567890123",
                    "description": "Contrato revisado com novas cláusulas",
                },
            )
        ],
    )
    def update(self, request, public_id=None):
        """Atualizar arquivo existente."""
        try:
            return super().update(request, public_id)
        except Exception as e:
            logger.error(f"Erro ao atualizar arquivo anexado {public_id}: {e}")
            return Response(
                {"error": "Erro interno ao processar atualização"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        summary="Atualizar parcialmente arquivo anexado",
        description="Atualização parcial com validação do Google Drive",
    )
    def partial_update(self, request, public_id=None):
        """Atualizar parcialmente arquivo existente."""
        try:
            return super().partial_update(request, public_id)
        except Exception as e:
            logger.error(
                f"Erro ao atualizar parcialmente arquivo anexado {public_id}: {e}"
            )
            return Response(
                {"error": "Erro interno ao processar atualização"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        summary="Excluir arquivo anexado",
        description="""
        Exclui arquivo anexado apenas se ele NÃO existir mais no Google Drive.
        
        **Importante:** Esta operação só é permitida quando o arquivo foi 
        removido do Google Drive externamente. Caso contrário, retornará erro.
        """,
        examples=[
            OpenApiExample(
                "Erro - Arquivo ainda existe",
                summary="Tentativa de exclusão com arquivo ainda no Drive",
                description="Resposta quando arquivo ainda existe no Google Drive",
                value={
                    "error": "Não é possível excluir: arquivo ainda existe no Google Drive"
                },
                response_only=True,
                status_codes=[400],
            )
        ],
    )
    def destroy(self, request, public_id=None):
        """Excluir arquivo (apenas se não existir no Google Drive)."""
        try:
            instance = self.get_object()
            AttachedFileService.delete_attached_file(instance)

            logger.info(f"Arquivo anexado {public_id} removido com sucesso")
            return Response(status=status.HTTP_204_NO_CONTENT)

        except Http404:
            logger.warning(
                f"Tentativa de deletar arquivo anexado inexistente: {public_id}"
            )
            return Response(
                {"error": "Arquivo não encontrado no banco de dados"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            logger.error(f"Erro ao excluir arquivo anexado {public_id}: {e}")

            # Extrair mensagem limpa da ValidationError
            if "ainda existe no Google Drive" in str(e):
                # Extrair mensagem do ErrorDetail se for uma ValidationError
                error_message = str(e)
                if "ErrorDetail" in error_message and "string=" in error_message:
                    # Extrair a mensagem entre aspas simples
                    import re

                    match = re.search(r"string='([^']*)'", error_message)
                    if match:
                        error_message = match.group(1)

                return Response(
                    {"error": error_message}, status=status.HTTP_400_BAD_REQUEST
                )

            return Response(
                {"error": "Erro interno ao processar exclusão"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        summary="Obter detalhes do arquivo",
        description="Retorna informações detalhadas do arquivo anexado",
    )
    def retrieve(self, request, public_id=None):
        """Obter detalhes de um arquivo específico."""
        return super().retrieve(request, public_id)
