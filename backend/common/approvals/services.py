from typing import Dict, Any, Optional, TYPE_CHECKING
from django.contrib.auth import get_user_model
from django.apps import apps
from django.core.exceptions import ObjectDoesNotExist
from common.audit.services import AuditService
from .models import ApprovalRequest

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser

User = get_user_model()


class ApprovalService:
    """
    Serviço para gerenciar solicitações de aprovação.
    """

    @staticmethod
    def create_request(
        subject: str,
        action: str,
        resource_type: str,
        resource_id: str,
        payload_diff: Dict[str, Any],
        reason: str,
        requested_by: "AbstractUser",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ApprovalRequest:
        """
        Cria uma nova solicitação de aprovação.
        """
        approval_request = ApprovalRequest.objects.create(
            subject=subject,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            payload_diff=payload_diff,
            reason=reason,
            requested_by=requested_by,
            metadata=metadata or {},
        )

        # Registrar criação da solicitação na auditoria
        AuditService.log_create(
            content_object=approval_request,
            user=requested_by,
            metadata={"type": "approval_request_created"},
        )

        return approval_request

    @staticmethod
    def approve_request(
        approval_request: ApprovalRequest, approved_by: "AbstractUser", notes: str = ""
    ) -> bool:
        """
        Aprova uma solicitação e executa a mudança.
        """
        if not approval_request.is_pending:
            return False

        # Aprovar a solicitação
        approval_request.approve(approved_by, notes)

        # Registrar aprovação na auditoria
        AuditService.log_update(
            content_object=approval_request,
            old_data={"status": "pending"},
            user=approved_by,
            metadata={"type": "approval_request_approved", "notes": notes},
        )

        # Executar a mudança
        try:
            ApprovalService._execute_change(approval_request)
            return True
        except Exception as e:
            # Se a execução falhar, registrar o erro
            AuditService.log_action(
                action="ERROR",
                content_object=approval_request,
                user=approved_by,
                metadata={"type": "approval_request_execution_failed", "error": str(e)},
            )
            raise

    @staticmethod
    def reject_request(
        approval_request: ApprovalRequest, approved_by: "AbstractUser", notes: str = ""
    ) -> bool:
        """
        Rejeita uma solicitação.
        """
        if not approval_request.is_pending:
            return False

        # Rejeitar a solicitação
        approval_request.reject(approved_by, notes)

        # Registrar rejeição na auditoria
        AuditService.log_update(
            content_object=approval_request,
            old_data={"status": "pending"},
            user=approved_by,
            metadata={"type": "approval_request_rejected", "notes": notes},
        )

        return True

    @staticmethod
    def _execute_change(approval_request: ApprovalRequest):
        """
        Executa a mudança especificada na solicitação de aprovação.
        """
        # Obter o modelo alvo
        app_label, model_name = approval_request.resource_type.split(".")
        model_class = apps.get_model(app_label, model_name)

        try:
            # Obter o objeto alvo
            if approval_request.action == ApprovalRequest.ApprovalAction.CREATE:
                # Para CREATE, o objeto ainda não existe
                obj = model_class(**approval_request.payload_diff.get("new_data", {}))
                obj.save()

                # Registrar criação na auditoria
                AuditService.log_create(
                    content_object=obj,
                    metadata={
                        "type": "executed_via_approval",
                        "approval_request_id": str(approval_request.id),
                    },
                )

            else:
                # Para UPDATE/DELETE, o objeto deve existir
                obj = model_class.objects.get(pk=approval_request.resource_id)
                old_data = AuditService._serialize_object(obj)

                if approval_request.action == ApprovalRequest.ApprovalAction.UPDATE:
                    # Atualizar campos especificados
                    new_data = approval_request.payload_diff.get("new_data", {})
                    for field, value in new_data.items():
                        setattr(obj, field, value)
                    obj.save()

                    # Registrar atualização na auditoria
                    AuditService.log_update(
                        content_object=obj,
                        old_data=old_data,
                        metadata={
                            "type": "executed_via_approval",
                            "approval_request_id": str(approval_request.id),
                        },
                    )

                elif approval_request.action == ApprovalRequest.ApprovalAction.DELETE:
                    # Excluir objeto
                    AuditService.log_delete(
                        content_object=obj,
                        metadata={
                            "type": "executed_via_approval",
                            "approval_request_id": str(approval_request.id),
                        },
                    )
                    obj.delete()

                elif approval_request.action in [
                    ApprovalRequest.ApprovalAction.ACTIVATE,
                    ApprovalRequest.ApprovalAction.DEACTIVATE,
                ]:
                    # Ações de ativação/desativação
                    is_active = (
                        approval_request.action == ApprovalRequest.ApprovalAction.ACTIVATE
                    )
                    if hasattr(obj, "is_active"):
                        obj.is_active = is_active
                        obj.save()

                        AuditService.log_update(
                            content_object=obj,
                            old_data=old_data,
                            metadata={
                                "type": "executed_via_approval",
                                "approval_request_id": str(approval_request.id),
                                "action": approval_request.action,
                            },
                        )

            # Marcar solicitação como executada
            approval_request.mark_executed()

            # Registrar execução na auditoria
            AuditService.log_update(
                content_object=approval_request,
                old_data={"status": "approved"},
                metadata={"type": "approval_request_executed"},
            )

        except ObjectDoesNotExist:
            raise ValueError(
                f"Objeto {approval_request.resource_type} com ID {approval_request.resource_id} não encontrado"
            )
        except Exception as e:
            raise ValueError(f"Erro ao executar mudança: {str(e)}")
