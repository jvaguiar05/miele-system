from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.db import models
from common.audit.services import AuditService


class AuditableMixin:
    """
    Mixin para modelos que devem ser auditados automaticamente.
    """

    def get_audit_exempt_fields(self):
        """
        Retorna lista de campos que devem ser ignorados na auditoria.
        """
        return ["updated_at", "last_login", "password"]


@receiver(pre_save)
def capture_pre_save_data(sender, instance, **kwargs):
    """
    Captura o estado anterior do objeto antes da atualização.
    """
    # Verificar se o modelo deve ser auditado
    if not hasattr(instance, "__audit__") or not getattr(instance, "__audit__", True):
        return

    # Apenas para atualizações (objeto já existe)
    if instance.pk:
        try:
            # Obter estado anterior do banco
            old_instance = sender.objects.get(pk=instance.pk)
            instance._audit_old_data = AuditService._serialize_object(old_instance)
        except sender.DoesNotExist:
            instance._audit_old_data = None
    else:
        instance._audit_old_data = None


@receiver(post_save)
def audit_post_save(sender, instance, created, **kwargs):
    """
    Audita criações e atualizações de objetos.
    """
    # Verificar se o modelo deve ser auditado
    if not hasattr(instance, "__audit__") or not getattr(instance, "__audit__", True):
        return

    # Ignorar modelos de auditoria para evitar loops
    if sender.__name__ in ["AuditLog", "ApprovalRequest"]:
        return

    try:
        if created:
            # Objeto criado
            AuditService.log_create(
                content_object=instance, metadata={"type": "auto_audit_create"}
            )
        else:
            # Objeto atualizado
            old_data = getattr(instance, "_audit_old_data", None)
            if old_data:
                # Check if only exempt fields were changed
                exempt_fields = []
                if hasattr(instance, "get_audit_exempt_fields"):
                    exempt_fields = instance.get_audit_exempt_fields()
                elif hasattr(sender, "get_audit_exempt_fields"):
                    # If it's a class method
                    exempt_fields = sender.get_audit_exempt_fields()
                else:
                    # Default exempt fields
                    exempt_fields = ["updated_at", "last_login", "password"]

                # Get current data
                new_data = AuditService._serialize_object(instance)

                # Check if any non-exempt fields changed
                significant_changes = False
                for field, new_value in new_data.items():
                    if field not in exempt_fields:
                        old_value = old_data.get(field)
                        if old_value != new_value:
                            significant_changes = True
                            break

                # Only log if there are significant changes
                if significant_changes:
                    AuditService.log_update(
                        content_object=instance,
                        old_data=old_data,
                        metadata={"type": "auto_audit_update"},
                    )
    except Exception as e:
        # Log do erro, mas não interromper o processo principal
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Erro na auditoria automática: {e}")


@receiver(post_delete)
def audit_post_delete(sender, instance, **kwargs):
    """
    Audita exclusões de objetos.
    """
    # Verificar se o modelo deve ser auditado
    if not hasattr(instance, "__audit__") or not getattr(instance, "__audit__", True):
        return

    # Ignorar modelos de auditoria para evitar loops
    if sender.__name__ in ["AuditLog", "ApprovalRequest"]:
        return

    try:
        AuditService.log_delete(
            content_object=instance, metadata={"type": "auto_audit_delete"}
        )
    except Exception as e:
        # Log do erro, mas não interromper o processo principal
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Erro na auditoria automática: {e}")
