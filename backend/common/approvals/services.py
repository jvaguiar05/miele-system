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

        # ApprovalRequest creation is not logged in audit system
        # since the ApprovalRequest itself serves as the audit trail

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

        # Aprovar e executar a solicitação
        try:
            ApprovalService._execute_change(approval_request, approved_by)
            # Mark as approved and executed after successful execution
            approval_request.approve_and_execute(approved_by, notes)
            return True
        except Exception as e:
            # Execution failed - error info is stored in ApprovalRequest itself
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
        approval_request.reject_and_execute(approved_by, notes)

        # Handle special rejection cases
        if (
            approval_request.resource_type == "identity.User"
            and approval_request.action == "activate"
        ):
            # For user activation rejection, set the user status to declined
            try:
                app_label, model_name = approval_request.resource_type.split(".")
                model_class = apps.get_model(app_label, model_name)
                user = model_class.objects.get(pk=approval_request.resource_id)

                # Capture complete old data for audit log using the same serialization method
                from common.audit.services import AuditService

                old_data = AuditService._serialize_object(user)
                old_data = AuditService._filter_relevant_data(old_data)

                # Set user as declined and inactive
                user.approval_status = "declined"
                user.is_active = False

                # Temporarily disable automatic audit for this save
                user.__audit__ = False
                user.save()
                # Re-enable audit for future operations
                user.__audit__ = True

                # Log the user status change with proper old/new data
                AuditService.log_update(
                    content_object=user,
                    old_data=old_data,
                    user=approved_by,
                    metadata={
                        "type": "user_activation_rejected",
                        "approval_request_id": str(approval_request.id),
                    },
                )

            except Exception as e:
                # Error info is stored in ApprovalRequest status/metadata
                pass

        # ApprovalRequest rejection is not logged since the ApprovalRequest serves as audit trail

        return True

    @staticmethod
    def _execute_change(approval_request: ApprovalRequest, approved_by: "AbstractUser"):
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
                # Temporarily disable automatic audit for this save
                obj.__audit__ = False
                obj.save()
                # Re-enable audit for future operations
                obj.__audit__ = True

                # Registrar criação na auditoria
                AuditService.log_create(
                    content_object=obj,
                    user=approved_by,
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
                    # Temporarily disable automatic audit for this save
                    obj.__audit__ = False
                    obj.save()
                    # Re-enable audit for future operations
                    obj.__audit__ = True

                    # Registrar atualização na auditoria
                    AuditService.log_update(
                        content_object=obj,
                        old_data=old_data,
                        user=approved_by,
                        metadata={
                            "type": "executed_via_approval",
                            "approval_request_id": str(approval_request.id),
                        },
                    )

                elif approval_request.action == ApprovalRequest.ApprovalAction.DELETE:
                    # Excluir objeto
                    AuditService.log_delete(
                        content_object=obj,
                        user=approved_by,
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
                        approval_request.action
                        == ApprovalRequest.ApprovalAction.ACTIVATE
                    )

                    # Handle user activation specifically
                    if approval_request.resource_type == "identity.User":
                        # For user activation, update both is_active and approval_status
                        if is_active:
                            obj.is_active = True
                            obj.approval_status = "approved"
                        else:
                            obj.is_active = False
                            obj.approval_status = "declined"
                        # Temporarily disable automatic audit for this save
                        obj.__audit__ = False
                        obj.save()
                        # Re-enable audit for future operations
                        obj.__audit__ = True

                        # Log the user status change
                        AuditService.log_update(
                            content_object=obj,
                            old_data=old_data,
                            user=approved_by,
                            metadata={
                                "type": "executed_via_approval",
                                "approval_request_id": str(approval_request.id),
                                "action": approval_request.action,
                            },
                        )
                    elif hasattr(obj, "is_active"):
                        # For other objects, just update is_active
                        obj.is_active = is_active
                        # Temporarily disable automatic audit for this save
                        obj.__audit__ = False
                        obj.save()
                        # Re-enable audit for future operations
                        obj.__audit__ = True

                        AuditService.log_update(
                            content_object=obj,
                            old_data=old_data,
                            user=approved_by,
                            metadata={
                                "type": "executed_via_approval",
                                "approval_request_id": str(approval_request.id),
                                "action": approval_request.action,
                            },
                        )

            # ApprovalRequest execution is not logged since the ApprovalRequest serves as audit trail
            # Note: The calling method should handle marking the request as executed

        except ObjectDoesNotExist:
            raise ValueError(
                f"Objeto {approval_request.resource_type} com ID {approval_request.resource_id} não encontrado"
            )
        except Exception as e:
            raise ValueError(f"Erro ao executar mudança: {str(e)}")
