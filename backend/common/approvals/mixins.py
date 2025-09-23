"""
Mixins para ViewSets que requerem aprovação para alterações sensíveis.
"""

from typing import List, Dict, Any, Optional
from rest_framework import status
from rest_framework.response import Response
from django.conf import settings
from common.approvals.services import ApprovalService
from common.utils import ApprovalHelper


class RequiresApprovalMixin:
    """
    Mixin para ViewSets que intercepta alterações em campos sensíveis
    e cria approval_request ao invés de executar diretamente.

    Usage:
        class ClientViewSet(RequiresApprovalMixin, viewsets.ModelViewSet):
            sensitive_fields = ['cnpj', 'razao_social', 'status']
            approval_resource_type = 'clients.Client'
    """

    # Configurações que devem ser definidas no ViewSet
    sensitive_fields: List[str] = []
    approval_resource_type: str = None
    approval_exempt_actions: List[str] = [
        "list",
        "retrieve",
    ]  # Ações que não precisam aprovação

    def update(self, request, *args, **kwargs):
        """Override update para interceptar mudanças sensíveis."""
        if self._requires_approval(request.data, **kwargs):
            return self._create_approval_request(request, "update", *args, **kwargs)
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        """Override partial_update para interceptar mudanças sensíveis."""
        if self._requires_approval(request.data, **kwargs):
            return self._create_approval_request(
                request, "partial_update", *args, **kwargs
            )
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """Override destroy para requerer aprovação."""
        return self._create_approval_request(request, "destroy", *args, **kwargs)

    def _requires_approval(self, data: Dict[str, Any], **kwargs) -> bool:
        """
        Verifica se os dados contêm campos sensíveis que requerem aprovação.
        """
        if not self.sensitive_fields:
            return False

        # Verificar se algum campo sensível está sendo alterado
        sensitive_changes = set(data.keys()) & set(self.sensitive_fields)

        if not sensitive_changes:
            return False

        # Se for update/partial_update, verificar se há mudança real nos valores
        if hasattr(self, "get_object"):
            try:
                current_object = self.get_object()
                for field in sensitive_changes:
                    current_value = getattr(current_object, field, None)
                    new_value = data.get(field)
                    if current_value != new_value:
                        return True
                return False
            except:
                # Se não conseguir obter objeto atual, assumir que requer aprovação
                return True

        return True

    def _create_approval_request(self, request, action: str, *args, **kwargs):
        """
        Cria uma solicitação de aprovação ao invés de executar a ação diretamente.
        """
        if not self.approval_resource_type:
            raise ValueError(
                f"approval_resource_type deve ser definido em {self.__class__.__name__}"
            )

        # Obter objeto atual (se existir)
        current_object = None
        resource_id = None
        old_data = {}

        if action in ["update", "partial_update", "destroy"]:
            try:
                current_object = self.get_object()
                resource_id = str(current_object.pk)
                # Capturar dados atuais dos campos sensíveis
                old_data = {
                    field: getattr(current_object, field, None)
                    for field in self.sensitive_fields
                }
            except:
                return Response(
                    {"error": "Objeto não encontrado"}, status=status.HTTP_404_NOT_FOUND
                )

        # Preparar dados da mudança
        if action == "destroy":
            subject = (
                f"Excluir {self.approval_resource_type.split('.')[-1]} {resource_id}"
            )
            approval_action = "delete"
            payload_diff = {"old_data": old_data}
            new_data = {}
        else:
            subject = f"Alterar {self.approval_resource_type.split('.')[-1]} {resource_id or 'novo'}"
            approval_action = (
                "update" if action in ["update", "partial_update"] else "create"
            )
            new_data = {
                k: v for k, v in request.data.items() if k in self.sensitive_fields
            }
            payload_diff = {"old_data": old_data, "new_data": new_data}

        # Gerar razão automática se não fornecida
        reason = request.data.get(
            "approval_reason",
            f"Alteração solicitada via API - campos: {', '.join(new_data.keys())}",
        )

        # Criar solicitação de aprovação
        try:
            approval_request = ApprovalService.create_request(
                subject=subject,
                action=approval_action,
                resource_type=self.approval_resource_type,
                resource_id=resource_id or "new",
                payload_diff=payload_diff,
                reason=reason,
                requested_by=request.user,
                metadata={
                    "api_endpoint": request.path,
                    "http_method": request.method,
                    "original_action": action,
                    "sensitive_fields_changed": list(new_data.keys()),
                },
            )

            return Response(
                {
                    "message": "Solicitação de aprovação criada. As alterações serão aplicadas após aprovação por um administrador.",
                    "approval_request": {
                        "id": approval_request.id,
                        "subject": approval_request.subject,
                        "status": approval_request.status,
                        "created_at": approval_request.created_at,
                    },
                    "next_steps": "Um administrador deve aprovar esta solicitação via /api/v1/admin/approval-requests/",
                },
                status=status.HTTP_202_ACCEPTED,
            )

        except Exception as e:
            return Response(
                {"error": f"Erro ao criar solicitação de aprovação: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def _get_sensitive_fields_from_settings(self) -> List[str]:
        """
        Obtém campos sensíveis das configurações do Django.
        """
        config = getattr(settings, "SENSITIVE_FIELDS_CONFIG", {})
        return config.get(self.approval_resource_type, self.sensitive_fields)


class AutoApprovalFieldsMixin(RequiresApprovalMixin):
    """
    Versão que obtém automaticamente os campos sensíveis das configurações.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.approval_resource_type:
            self.sensitive_fields = self._get_sensitive_fields_from_settings()
