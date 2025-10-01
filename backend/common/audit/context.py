import threading
from typing import Optional, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser

# Thread-local storage para dados de contexto
_context = threading.local()


def set_correlation_id(correlation_id: str) -> None:
    """Define o correlation_id para o contexto atual."""
    _context.correlation_id = correlation_id


def get_correlation_id() -> Optional[str]:
    """Obtém o correlation_id do contexto atual."""
    return getattr(_context, "correlation_id", None)


def set_current_user(user: "AbstractUser") -> None:
    """Define o usuário atual para o contexto."""
    _context.current_user = user


def get_current_user() -> Optional["AbstractUser"]:
    """Obtém o usuário atual do contexto."""
    return getattr(_context, "current_user", None)


def set_request_metadata(metadata: Dict[str, Any]) -> None:
    """Define metadados do request atual."""
    _context.request_metadata = metadata


def get_request_metadata() -> Optional[Dict[str, Any]]:
    """Obtém metadados do request atual."""
    return getattr(_context, "request_metadata", None)


def clear_context() -> None:
    """Limpa todos os dados do contexto atual."""
    for attr in ["correlation_id", "current_user", "request_metadata"]:
        if hasattr(_context, attr):
            delattr(_context, attr)


class AuditContext:
    """
    Context manager para definir dados de auditoria.
    """

    def __init__(
        self,
        correlation_id: str,
        user: "AbstractUser" = None,
        metadata: Dict[str, Any] = None,
    ):
        self.correlation_id = correlation_id
        self.user = user
        self.metadata = metadata or {}
        self.previous_correlation_id = None
        self.previous_user = None
        self.previous_metadata = None

    def __enter__(self):
        # Salvar contexto anterior
        self.previous_correlation_id = get_correlation_id()
        self.previous_user = get_current_user()
        self.previous_metadata = get_request_metadata()

        # Definir novo contexto
        set_correlation_id(self.correlation_id)
        if self.user:
            set_current_user(self.user)
        if self.metadata:
            set_request_metadata(self.metadata)

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Restaurar contexto anterior
        if self.previous_correlation_id:
            set_correlation_id(self.previous_correlation_id)
        if self.previous_user:
            set_current_user(self.previous_user)
        if self.previous_metadata:
            set_request_metadata(self.previous_metadata)
        else:
            clear_context()
