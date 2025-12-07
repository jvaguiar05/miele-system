import logging
from django.db.models.signals import post_delete
from django.dispatch import receiver
from common.shared.models import AttachedFile
from common.services.google_drive import drive_service

logger = logging.getLogger(__name__)


@receiver(post_delete, sender=AttachedFile)
def delete_file_from_drive(sender, instance, **kwargs):
    """
    Garante que, sempre que um registro AttachedFile for removido do banco
    (seja via API, Admin ou Cascade), o arquivo físico também seja
    removido do Google Drive.
    """
    if instance.drive_file_id:
        try:
            logger.info(
                f"Signal: Removendo arquivo do Drive {instance.drive_file_id} (Ref: {instance.file_name})"
            )
            drive_service.delete_file(instance.drive_file_id)
        except Exception as e:
            # Não queremos que um erro no Drive impeça a deleção no banco,
            # então apenas logamos o erro (Orphaned file warning).
            logger.warning(
                f"FALHA ao deletar arquivo órfão no Drive {instance.drive_file_id}: {e}"
            )
