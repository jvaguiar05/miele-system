"""
Service layer para lógica de negócio de arquivos anexados.
"""

import logging
from django.db import transaction
from django.core.exceptions import ValidationError
from rest_framework.exceptions import ValidationError as DRFValidationError
from django.contrib.contenttypes.models import ContentType

from common.services.google_drive import drive_service, GoogleDriveServiceError
from .models import AttachedFile

logger = logging.getLogger(__name__)


class AttachedFileService:
    """Service centralizado para operações de arquivos anexados."""

    @staticmethod
    def validate_drive_file_exists(drive_file_id: str) -> bool:
        """
        Valida se arquivo existe no Google Drive (usado em POST/PUT).

        Args:
            drive_file_id: ID do arquivo no Google Drive

        Returns:
            True se existe, False caso contrário

        Raises:
            DRFValidationError: Se houver erro de autenticação ou API
        """
        try:
            return drive_service.file_exists(drive_file_id)
        except GoogleDriveServiceError as e:
            logger.error(f"Erro ao validar arquivo no Drive {drive_file_id}: {e}")
            raise DRFValidationError(
                f"Erro ao verificar arquivo no Google Drive: {str(e)}"
            )

    @staticmethod
    def validate_drive_file_absent(drive_file_id: str) -> bool:
        """
        Valida se arquivo NÃO existe no Google Drive (usado em DELETE).

        Args:
            drive_file_id: ID do arquivo no Google Drive

        Returns:
            True se NÃO existe (pode deletar), False se ainda existe

        Raises:
            DRFValidationError: Se houver erro de autenticação ou API
        """
        try:
            logger.info(
                f"Verificando se arquivo {drive_file_id} foi removido do Google Drive"
            )
            exists = drive_service.file_exists(drive_file_id)
            logger.info(
                f"Resultado da verificação: arquivo {drive_file_id} {'existe' if exists else 'NÃO existe'} no Drive"
            )
            return not exists  # Retorna True se NÃO existe
        except GoogleDriveServiceError as e:
            logger.error(
                f"Erro ao verificar ausência do arquivo no Drive {drive_file_id}: {e}"
            )
            raise DRFValidationError(
                f"Erro ao verificar arquivo no Google Drive: {str(e)}"
            )

    @staticmethod
    def resolve_entity_from_public_id(object_id: str):
        """
        Resolve entidade (Client/PerDcomp) a partir do public_id.

        Args:
            object_id: Public ID da entidade (UUID)

        Returns:
            tuple: (entity_instance, entity_type, content_type)

        Raises:
            DRFValidationError: Se entidade não for encontrada
        """
        try:
            # Tentar Client primeiro
            from apps.clients.models import Client

            client = Client.objects.get(public_id=object_id, deleted_at__isnull=True)
            content_type = ContentType.objects.get_for_model(Client)
            return client, "client", content_type
        except Client.DoesNotExist:
            pass

        try:
            # Tentar PerDcomp
            from apps.perdcomps.models import PerDcomp

            perdcomp = PerDcomp.objects.get(
                public_id=object_id, deleted_at__isnull=True
            )
            content_type = ContentType.objects.get_for_model(PerDcomp)
            return perdcomp, "perdcomp", content_type
        except PerDcomp.DoesNotExist:
            pass

        raise DRFValidationError("Entidade não encontrada ou foi removida")

    @staticmethod
    def get_files_for_entity(object_id: str, file_type_filter: str = None):
        """
        Busca arquivos por entidade com filtros opcionais.

        Args:
            object_id: Public ID da entidade
            file_type_filter: Filtro opcional por tipo de arquivo

        Returns:
            QuerySet: Arquivos da entidade
        """
        entity, entity_type, content_type = (
            AttachedFileService.resolve_entity_from_public_id(object_id)
        )

        queryset = AttachedFile.objects.filter(
            content_type=content_type,
            object_id=entity.id,
            sync_status__in=["synced", "pending"],  # Apenas arquivos acessíveis
        ).select_related("content_type")

        if file_type_filter:
            queryset = queryset.filter(file_type__icontains=file_type_filter)

        return queryset

    @staticmethod
    @transaction.atomic
    def create_attached_file(validated_data, user):
        """
        Cria arquivo anexado com validações completas.

        Args:
            validated_data: Dados validados do serializer
            user: Usuário que está criando o arquivo

        Returns:
            AttachedFile: Instância criada
        """
        object_id = validated_data.pop("object_id")
        drive_file_id = validated_data.get("drive_file_id")

        # Validar arquivo existe no Drive
        if not AttachedFileService.validate_drive_file_exists(drive_file_id):
            raise DRFValidationError(
                {"drive_file_id": "Arquivo não encontrado no Google Drive"}
            )

        # Resolver entidade
        entity, entity_type, content_type = (
            AttachedFileService.resolve_entity_from_public_id(object_id)
        )

        # Verificar duplicação de drive_file_id
        if AttachedFile.objects.filter(drive_file_id=drive_file_id).exists():
            raise DRFValidationError(
                {"drive_file_id": "Este arquivo já está registrado no sistema"}
            )

        # Criar arquivo
        attached_file = AttachedFile.objects.create(
            content_type=content_type,
            object_id=entity.id,
            uploaded_by_id=user.id,
            sync_status="synced",
            **validated_data,
        )

        logger.info(
            f"Arquivo anexado criado: {attached_file.public_id} para {entity_type} {entity.public_id}"
        )
        return attached_file

    @staticmethod
    @transaction.atomic
    def update_attached_file(instance, validated_data):
        """
        Atualiza arquivo anexado com validações.

        Args:
            instance: Instância do AttachedFile
            validated_data: Dados validados do serializer

        Returns:
            AttachedFile: Instância atualizada
        """
        try:
            logger.info(
                f"Iniciando atualização do arquivo {instance.public_id} com dados: {validated_data}"
            )

            drive_file_id = validated_data.get("drive_file_id")

            # Se drive_file_id foi alterado, validar
            if drive_file_id and drive_file_id != instance.drive_file_id:
                logger.info(
                    f"drive_file_id alterado de {instance.drive_file_id} para {drive_file_id}"
                )

                # Validar arquivo existe no Drive
                if not AttachedFileService.validate_drive_file_exists(drive_file_id):
                    raise DRFValidationError(
                        {"drive_file_id": "Arquivo não encontrado no Google Drive"}
                    )

                # Verificar duplicação (excluindo a própria instância)
                if (
                    AttachedFile.objects.filter(drive_file_id=drive_file_id)
                    .exclude(pk=instance.pk)
                    .exists()
                ):
                    raise DRFValidationError(
                        {"drive_file_id": "Este arquivo já está registrado no sistema"}
                    )

            # Atualizar campos
            for field, value in validated_data.items():
                logger.info(f"Atualizando campo {field}: {value}")
                setattr(instance, field, value)

            instance.save()

            logger.info(f"Arquivo anexado atualizado: {instance.public_id}")
            return instance

        except Exception as e:
            logger.error(
                f"Erro detalhado ao atualizar arquivo {instance.public_id}: {type(e).__name__}: {str(e)}"
            )
            raise

    @staticmethod
    @transaction.atomic
    def delete_attached_file(instance):
        """
        Remove arquivo apenas se não existir mais no Google Drive.

        Args:
            instance: Instância do AttachedFile

        Raises:
            DRFValidationError: Se arquivo ainda existe no Drive
        """
        drive_file_id = instance.drive_file_id

        # Validar que arquivo NÃO existe no Drive (frontend já removeu)
        if not AttachedFileService.validate_drive_file_absent(drive_file_id):
            raise DRFValidationError(
                "Não é possível excluir: arquivo ainda existe no Google Drive"
            )

        file_id = instance.public_id
        instance.delete()

        logger.info(
            f"Arquivo anexado removido: {file_id} (drive_file_id: {drive_file_id})"
        )
