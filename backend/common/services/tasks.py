"""
Celery tasks para sincronização com Google Drive.
"""

import logging
from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from django.conf import settings

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def sync_drive_files(self):
    """
    Task para verificar sincronização com Google Drive.

    - Verifica se arquivos ainda existem no Drive
    - Remove registros de arquivos deletados
    """
    from common.shared.models import AttachedFile
    from common.services.google_drive import drive_service

    try:
        logger.info("Iniciando verificação de sincronização com Google Drive")

        # Buscar todos os arquivos sincronizados
        files_to_verify = AttachedFile.objects.filter(sync_status="synced")

        verified_count = 0
        deleted_count = 0
        error_count = 0

        for attached_file in files_to_verify:
            try:
                # Verificar se arquivo existe no Drive
                if drive_service.file_exists(attached_file.drive_file_id):
                    # Arquivo existe - continua sincronizado
                    verified_count += 1
                else:
                    # Arquivo não existe no Drive - remover registro
                    attached_file.delete()
                    deleted_count += 1

                    logger.info(
                        f"Registro removido - arquivo não existe mais no Drive: {attached_file.drive_file_id}"
                    )

            except Exception as e:
                # Erro ao verificar arquivo específico
                attached_file.mark_sync_error()
                error_count += 1

                logger.error(
                    f"Erro ao verificar arquivo {attached_file.drive_file_id}: {e}"
                )

        logger.info(
            f"Sincronização concluída: {verified_count} verificados, "
            f"{deleted_count} deletados, {error_count} erros"
        )

        return {
            "verified_count": verified_count,
            "deleted_count": deleted_count,
            "error_count": error_count,
            "total_processed": verified_count + deleted_count + error_count,
        }

    except Exception as exc:
        logger.error(f"Erro na sincronização com Google Drive: {exc}")

        # Retry com backoff exponencial
        raise self.retry(
            exc=exc, countdown=60 * (2**self.request.retries), max_retries=3
        )


@shared_task
def cleanup_orphaned_files():
    """
    Task para limpeza de arquivos órfãos no sistema.

    Remove registros de arquivos que:
    - Estão com status 'error' há mais de 7 dias sem correção
    """
    from common.shared.models import AttachedFile

    try:
        logger.info("Iniciando limpeza de arquivos órfãos")

        # Arquivos com erro há mais de 7 dias
        old_error_threshold = timezone.now() - timedelta(days=7)
        old_error_files = AttachedFile.objects.filter(
            sync_status="error", updated_at__lt=old_error_threshold
        )

        error_count = old_error_files.count()

        # Remover registros órfãos
        old_error_files.delete()

        logger.info(f"Limpeza concluída: {error_count} registros com erro removidos")

        return {"error_count": error_count, "total_cleaned": error_count}

    except Exception as e:
        logger.error(f"Erro na limpeza de arquivos órfãos: {e}")
        raise


@shared_task
def validate_drive_permissions():
    """
    Task para validar permissões de acesso aos arquivos no Google Drive.

    Verifica se a service account ainda tem acesso aos arquivos
    e se as pastas base ainda existem.
    """
    from common.services.google_drive import drive_service

    try:
        logger.info("Validando permissões do Google Drive")

        # Verificar acesso às pastas base
        base_folders = {
            "clients": getattr(settings, "GDRIVE_CLIENTS_FOLDER_ID", None),
            "perdcomps": getattr(settings, "GDRIVE_PERDCOMPS_FOLDER_ID", None),
        }

        results = {}

        for folder_type, folder_id in base_folders.items():
            if folder_id:
                try:
                    folder_exists = drive_service.file_exists(folder_id)
                    results[f"{folder_type}_folder"] = {
                        "exists": folder_exists,
                        "folder_id": folder_id,
                    }

                    if not folder_exists:
                        logger.error(
                            f"Pasta base {folder_type} não encontrada: {folder_id}"
                        )

                except Exception as e:
                    logger.error(f"Erro ao verificar pasta {folder_type}: {e}")
                    results[f"{folder_type}_folder"] = {
                        "exists": False,
                        "error": str(e),
                    }
            else:
                logger.warning(f"ID da pasta {folder_type} não configurado")
                results[f"{folder_type}_folder"] = {
                    "exists": False,
                    "error": "Não configurado",
                }

        logger.info(f"Validação de permissões concluída: {results}")
        return results

    except Exception as e:
        logger.error(f"Erro na validação de permissões: {e}")
        raise


# Configuração de tasks periódicas (para ser usado no beat schedule)
GOOGLE_DRIVE_CELERY_BEAT_SCHEDULE = {
    "sync-drive-files": {
        "task": "common.services.tasks.sync_drive_files",
        "schedule": 3600.0,  # A cada hora
        "options": {
            "expires": 3000,  # Expira em 50 minutos se não executar
        },
    },
    "cleanup-orphaned-files": {
        "task": "common.services.tasks.cleanup_orphaned_files",
        "schedule": 86400.0,  # Uma vez por dia
        "options": {
            "expires": 43200,  # Expira em 12 horas
        },
    },
    "validate-drive-permissions": {
        "task": "common.services.tasks.validate_drive_permissions",
        "schedule": 21600.0,  # A cada 6 horas
        "options": {
            "expires": 10800,  # Expira em 3 horas
        },
    },
}
