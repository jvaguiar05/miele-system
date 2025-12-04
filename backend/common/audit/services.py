import json
import re
from typing import Any, Dict, Optional
from django.contrib.contenttypes.models import ContentType
from django.core.serializers.json import DjangoJSONEncoder
from django.utils.dateparse import parse_datetime, parse_date
from datetime import datetime, date, time
from decimal import Decimal, InvalidOperation
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
            user = AuditService._get_current_user()

        correlation_id = get_correlation_id()
        # Se não houver correlation_id no contexto, gerar um novo (para comandos Django)
        if correlation_id is None:
            import uuid

            correlation_id = str(uuid.uuid4())

        request_metadata = get_request_metadata()

        # Preparar metadata
        final_metadata = metadata or {}
        if request_metadata:
            final_metadata.update(request_metadata)

        # Adicionar informações de debug sobre o usuário
        if user:
            final_metadata.update(
                {
                    "user_id": user.id,
                    "username": getattr(user, "username", str(user)),
                    "user_source": "context" if get_current_user() else "parameter",
                }
            )
        else:
            final_metadata["user_source"] = "none_found"

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
        new_data = AuditService._filter_relevant_data(new_data)
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
        new_data = AuditService._filter_relevant_data(new_data)
        old_data = AuditService._filter_relevant_data(old_data)

        # Filter to only include changed fields with smart comparison
        old_data_filtered = {}
        new_data_filtered = {}

        for field, new_value in new_data.items():
            old_value = old_data.get(field)
            if AuditService._values_are_different(field, old_value, new_value):
                old_data_filtered[field] = old_value
                new_data_filtered[field] = new_value

        return AuditService.log_action(
            action=AuditLog.AuditAction.UPDATE,
            content_object=content_object,
            old_data=old_data_filtered,
            new_data=new_data_filtered,
            user=user,
            metadata=metadata,
        )

    @staticmethod
    def _values_are_different(field_name: str, old_value: Any, new_value: Any) -> bool:
        """
        Compara dois valores de forma inteligente, considerando tipos especiais.

        Args:
            field_name: Nome do campo (usado para heurísticas específicas)
            old_value: Valor antigo
            new_value: Valor novo

        Returns:
            True se os valores são diferentes, False caso contrário
        """
        # Se os valores são exatamente iguais
        if old_value == new_value:
            return False

        # Se um é None e outro não, são diferentes
        if (old_value is None) != (new_value is None):
            return True

        # Se ambos são None, são iguais
        if old_value is None and new_value is None:
            return False

        # Normalizar e comparar datas/datetimes
        if AuditService._is_date_like_value(
            old_value
        ) or AuditService._is_date_like_value(new_value):
            return AuditService._compare_date_values(old_value, new_value)

        # Comparar strings (remove espaços extras)
        if isinstance(old_value, str) and isinstance(new_value, str):
            return old_value.strip() != new_value.strip()

        # Comparar números (pode incluir diferentes tipos: int, float, Decimal)
        if isinstance(old_value, (int, float, Decimal)) and isinstance(
            new_value, (int, float, Decimal)
        ):
            try:
                return Decimal(str(old_value)) != Decimal(str(new_value))
            except (ValueError, InvalidOperation):
                pass

        # Fallback: comparação direta
        return old_value != new_value

    @staticmethod
    def _is_date_like_value(value: Any) -> bool:
        """Verifica se um valor parece ser uma data."""
        if isinstance(value, (date, datetime)):
            return True
        if isinstance(value, str):
            # Verifica se a string está no formato ISO de data
            return bool(re.match(r"\d{4}-\d{2}-\d{2}", value))
        return False

    @staticmethod
    def _compare_date_values(old_value: Any, new_value: Any) -> bool:
        """
        Compara valores de data/datetime de forma normalizada.

        Returns:
            True se são diferentes, False se são iguais
        """

        def normalize_date_value(value):
            if value is None:
                return None
            if isinstance(value, datetime):
                # Converter para date se não tem tempo significativo
                if value.time() == time.min:
                    return value.date()
                return value.replace(microsecond=0)  # Remove microsegundos
            if isinstance(value, date):
                return value
            if isinstance(value, str):
                try:
                    # Tentar parsear como datetime primeiro
                    if "T" in value or " " in value:
                        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                        # Se o tempo é midnight, converter para date
                        if parsed.time() == time.min:
                            return parsed.date()
                        return parsed.replace(microsecond=0)
                    else:
                        # Parsear como date
                        return datetime.strptime(value[:10], "%Y-%m-%d").date()
                except (ValueError, TypeError):
                    pass
            return value

        normalized_old = normalize_date_value(old_value)
        normalized_new = normalize_date_value(new_value)

        return normalized_old != normalized_new

    @staticmethod
    def log_action(
        action: str,
        content_object: Any,
        old_data: Optional[Dict] = None,
        new_data: Optional[Dict] = None,
        user=None,
        metadata: Optional[Dict] = None,
    ) -> AuditLog:
        """Método central para registrar ações de auditoria."""
        from django.contrib.contenttypes.models import ContentType

        content_type = ContentType.objects.get_for_model(content_object)

        # Obter o usuário do contexto se não fornecido
        if user is None:
            user = get_current_user()

        correlation_id = get_correlation_id()

        # Se correlation_id é None, gerar um UUID
        if correlation_id is None:
            import uuid

            correlation_id = str(uuid.uuid4())

        return AuditLog.objects.create(
            action=action,
            content_type=content_type,
            object_id=content_object.pk,
            old_data=old_data or {},
            new_data=new_data or {},
            user=user,
            correlation_id=correlation_id,
            metadata=metadata or {},
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
                    # Skip fields that are typically not relevant for audit logs
                    if (
                        field.name in ["password", "last_login", "date_joined"]
                        and value is None
                    ):
                        continue

                    # Converter valores para formato JSON-serializável
                    if value is None:
                        data[field.name] = None
                    else:
                        # Usar DjangoJSONEncoder para converter tipos complexos
                        encoder = DjangoJSONEncoder()
                        try:
                            # Tentar converter o valor usando o encoder
                            serialized_value = encoder.default(value)
                            data[field.name] = serialized_value
                        except TypeError:
                            # Se o encoder não conseguir converter, usar o valor original
                            # (tipos básicos como string, int, float, bool)
                            try:
                                json.dumps(value)
                                data[field.name] = value
                            except (TypeError, ValueError):
                                # Como último recurso, converter para string
                                data[field.name] = str(value)
                return data
            else:
                # Para outros objetos
                return {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}
        else:
            return {"value": str(obj)}

    @staticmethod
    def _get_current_user():
        """
        Tenta obter o usuário atual de múltiplas fontes.
        """
        # Primeiro, tentar do contexto de auditoria
        user = get_current_user()
        if user:
            return user

        # Se não conseguir do contexto, tentar o thread-local do middleware
        try:
            from core.middleware import get_current_request

            request = get_current_request()
            if request and hasattr(request, "user") and request.user.is_authenticated:
                return request.user
        except Exception:
            pass

        # Se não conseguir do contexto, tentar do thread local do Django
        try:
            import threading

            # Tentar acessar o request atual via thread local (usado por alguns middlewares)
            current_request = getattr(threading.current_thread(), "request", None)
            if (
                current_request
                and hasattr(current_request, "user")
                and current_request.user.is_authenticated
            ):
                return current_request.user
        except:
            pass

        return None

    @staticmethod
    def _filter_relevant_data(data: Dict) -> Dict:
        """
        Filtra dados para manter apenas informações relevantes para auditoria.
        Remove campos com valores None, vazios ou irrelevantes.
        """
        filtered = {}
        # Campos que devem ser sempre ignorados nos logs de auditoria
        irrelevant_fields = [
            "password", 
            "_state", 
            "updated_at",  # Campo de timestamp automático
            "last_login",   # Campo de controle interno
        ]

        for key, value in data.items():
            # Skip irrelevant fields
            if key in irrelevant_fields:
                continue
            # Skip None values for certain fields
            if value is None and key in ["date_joined"]:
                continue
            # Include all other fields
            filtered[key] = value

        return filtered
