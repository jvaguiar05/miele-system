import json
from typing import Any, Dict, Optional
from django.contrib.contenttypes.models import ContentType
from django.core.serializers.json import DjangoJSONEncoder
from .models import AuditLog
from .context import get_correlation_id, get_current_user, get_request_metadata


class AuditService:
    """
    Serviço responsável por registrar ações de auditoria.
    """

    @staticmethod
    def log_action(
        action: str,
        content_object: Any,
        old_data: Optional[Dict] = None,
        new_data: Optional[Dict] = None,
        user=None,
        metadata: Optional[Dict] = None,
    ) -> AuditLog:
        """
        Registra uma ação de auditoria.

        Args:
            action: Tipo de ação (CREATE, UPDATE, DELETE, etc.)
            content_object: Objeto Django que foi modificado
            old_data: Estado anterior do objeto (para UPDATE/DELETE)
            new_data: Novo estado do objeto (para CREATE/UPDATE)
            user: Usuário que executou a ação (se não fornecido, tenta obter do contexto)
            metadata: Informações adicionais sobre a ação

        Returns:
            AuditLog: Registro de auditoria criado
        """
        # Obter informações do contexto se não fornecidas
        if user is None:
            user = get_current_user()

        correlation_id = get_correlation_id()
        request_metadata = get_request_metadata()

        # Preparar metadata
        final_metadata = metadata or {}
        if request_metadata:
            final_metadata.update(request_metadata)

        # Obter ContentType do objeto
        content_type = ContentType.objects.get_for_model(content_object)
        object_id = str(content_object.pk)

        # Criar registro de auditoria
        audit_log = AuditLog.objects.create(
            correlation_id=correlation_id,
            user=user,
            action=action,
            content_type=content_type,
            object_id=object_id,
            old_data=old_data,
            new_data=new_data,
            metadata=final_metadata,
            ip_address=request_metadata.get("ip_address") if request_metadata else None,
            user_agent=request_metadata.get("user_agent") if request_metadata else None,
        )

        return audit_log

    @staticmethod
    def log_create(
        content_object: Any, user=None, metadata: Optional[Dict] = None
    ) -> AuditLog:
        """Registra uma ação de criação."""
        new_data = AuditService._serialize_object(content_object)
        return AuditService.log_action(
            action=AuditLog.AuditAction.CREATE,
            content_object=content_object,
            new_data=new_data,
            user=user,
            metadata=metadata,
        )

    @staticmethod
    def log_update(
        content_object: Any, old_data: Dict, user=None, metadata: Optional[Dict] = None
    ) -> AuditLog:
        """Registra uma ação de atualização."""
        new_data = AuditService._serialize_object(content_object)
        return AuditService.log_action(
            action=AuditLog.AuditAction.UPDATE,
            content_object=content_object,
            old_data=old_data,
            new_data=new_data,
            user=user,
            metadata=metadata,
        )

    @staticmethod
    def log_delete(
        content_object: Any, user=None, metadata: Optional[Dict] = None
    ) -> AuditLog:
        """Registra uma ação de exclusão."""
        old_data = AuditService._serialize_object(content_object)
        return AuditService.log_action(
            action=AuditLog.AuditAction.DELETE,
            content_object=content_object,
            old_data=old_data,
            user=user,
            metadata=metadata,
        )

    @staticmethod
    def _serialize_object(obj: Any) -> Dict:
        """
        Serializa um objeto Django para JSON.

        Args:
            obj: Objeto a ser serializado

        Returns:
            Dict: Representação do objeto em dicionário
        """
        if hasattr(obj, "__dict__"):
            # Para modelos Django, extrair apenas os campos
            if hasattr(obj, "_meta"):
                data = {}
                for field in obj._meta.fields:
                    value = getattr(obj, field.name)
                    # Converter valores para formato JSON-serializável
                    try:
                        json.dumps(value, cls=DjangoJSONEncoder)
                        data[field.name] = value
                    except (TypeError, ValueError):
                        data[field.name] = str(value)
                return data
            else:
                # Para outros objetos
                return {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}
        else:
            return {"value": str(obj)}
