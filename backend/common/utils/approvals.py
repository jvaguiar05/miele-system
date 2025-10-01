from typing import Dict, Any, Optional, TYPE_CHECKING
from django.contrib.auth import get_user_model
from common.approvals.models import ApprovalRequest
from common.approvals.services import ApprovalService

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser

User = get_user_model()


class ApprovalHelper:
    """
    Helper para simplificar a criação de solicitações de aprovação.
    """

    @staticmethod
    def request_user_activation(
        user_id: str, requested_by: "AbstractUser", reason: str = ""
    ) -> ApprovalRequest:
        """
        Cria solicitação de aprovação para ativação de usuário.
        """
        return ApprovalService.create_request(
            subject=f"Ativar usuário {user_id}",
            action=ApprovalRequest.ApprovalAction.ACTIVATE,
            resource_type="identity.User",
            resource_id=user_id,
            payload_diff={"new_data": {"is_active": True}},
            reason=reason or "Solicitação de ativação de usuário",
            requested_by=requested_by,
            metadata={"type": "user_activation"},
        )

    @staticmethod
    def request_user_deactivation(
        user_id: str, requested_by: "AbstractUser", reason: str = ""
    ) -> ApprovalRequest:
        """
        Cria solicitação de aprovação para desativação de usuário.
        """
        return ApprovalService.create_request(
            subject=f"Desativar usuário {user_id}",
            action=ApprovalRequest.ApprovalAction.DEACTIVATE,
            resource_type="identity.User",
            resource_id=user_id,
            payload_diff={"new_data": {"is_active": False}},
            reason=reason or "Solicitação de desativação de usuário",
            requested_by=requested_by,
            metadata={"type": "user_deactivation"},
        )

    @staticmethod
    def request_user_role_change(
        user_id: str, new_role: str, requested_by: "AbstractUser", reason: str = ""
    ) -> ApprovalRequest:
        """
        Cria solicitação de aprovação para mudança de role de usuário.
        """
        try:
            user = User.objects.get(pk=user_id)
            old_role = user.role
        except User.DoesNotExist:
            old_role = None

        return ApprovalService.create_request(
            subject=f"Alterar role do usuário {user_id} para {new_role}",
            action=ApprovalRequest.ApprovalAction.UPDATE,
            resource_type="identity.User",
            resource_id=user_id,
            payload_diff={
                "old_data": {"role": old_role},
                "new_data": {"role": new_role},
            },
            reason=reason or f"Solicitação de mudança de role para {new_role}",
            requested_by=requested_by,
            metadata={"type": "user_role_change", "new_role": new_role},
        )

    @staticmethod
    def request_client_activation(
        client_id: str, requested_by: "AbstractUser", reason: str = ""
    ) -> ApprovalRequest:
        """
        Cria solicitação de aprovação para ativação de cliente.
        """
        return ApprovalService.create_request(
            subject=f"Ativar cliente {client_id}",
            action=ApprovalRequest.ApprovalAction.ACTIVATE,
            resource_type="clients.Client",
            resource_id=client_id,
            payload_diff={"new_data": {"is_active": True}},
            reason=reason or "Solicitação de ativação de cliente",
            requested_by=requested_by,
            metadata={"type": "client_activation"},
        )

    @staticmethod
    def request_client_deletion(
        client_id: str, requested_by: "AbstractUser", reason: str = ""
    ) -> ApprovalRequest:
        """
        Cria solicitação de aprovação para exclusão de cliente.
        """
        return ApprovalService.create_request(
            subject=f"Excluir cliente {client_id}",
            action=ApprovalRequest.ApprovalAction.DELETE,
            resource_type="clients.Client",
            resource_id=client_id,
            payload_diff={},
            reason=reason or "Solicitação de exclusão de cliente",
            requested_by=requested_by,
            metadata={"type": "client_deletion"},
        )

    @staticmethod
    def request_custom_action(
        subject: str,
        resource_type: str,
        resource_id: str,
        payload_diff: Dict[str, Any],
        requested_by: "AbstractUser",
        reason: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ApprovalRequest:
        """
        Cria solicitação de aprovação para ação personalizada.
        """
        return ApprovalService.create_request(
            subject=subject,
            action=ApprovalRequest.ApprovalAction.CUSTOM,
            resource_type=resource_type,
            resource_id=resource_id,
            payload_diff=payload_diff,
            reason=reason,
            requested_by=requested_by,
            metadata=metadata or {},
        )
