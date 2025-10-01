import uuid
from typing import Union


def generate_uuid() -> str:
    """Gera um UUID v4 como string."""
    return str(uuid.uuid4())


def is_valid_uuid(value: Union[str, uuid.UUID]) -> bool:
    """
    Verifica se um valor é um UUID válido.

    Args:
        value: String ou UUID para validar

    Returns:
        bool: True se for um UUID válido
    """
    try:
        if isinstance(value, str):
            uuid.UUID(value)
        elif isinstance(value, uuid.UUID):
            return True
        else:
            return False
        return True
    except (ValueError, TypeError):
        return False


def normalize_uuid(value: Union[str, uuid.UUID]) -> str:
    """
    Normaliza um UUID para string.

    Args:
        value: UUID ou string para normalizar

    Returns:
        str: UUID como string

    Raises:
        ValueError: Se o valor não for um UUID válido
    """
    if isinstance(value, uuid.UUID):
        return str(value)
    elif isinstance(value, str):
        if is_valid_uuid(value):
            return str(uuid.UUID(value))
        else:
            raise ValueError(f"Invalid UUID: {value}")
    else:
        raise ValueError(f"Invalid UUID type: {type(value)}")


def short_uuid() -> str:
    """
    Gera um UUID curto (8 caracteres) para IDs internos.

    Returns:
        str: UUID curto
    """
    return str(uuid.uuid4())[:8]
