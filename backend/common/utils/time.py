from datetime import datetime, timezone, timedelta
from typing import Optional, Union
from django.utils import timezone as django_timezone


def now() -> datetime:
    """Retorna o momento atual com timezone."""
    return django_timezone.now()


def utc_now() -> datetime:
    """Retorna o momento atual em UTC."""
    return datetime.now(timezone.utc)


def to_utc(dt: datetime) -> datetime:
    """
    Converte datetime para UTC.

    Args:
        dt: Datetime para converter

    Returns:
        datetime: Datetime em UTC
    """
    if dt.tzinfo is None:
        # Assume que é UTC se não tem timezone
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def format_datetime(dt: datetime, format_str: str = "%Y-%m-%d %H:%M:%S") -> str:
    """
    Formata datetime para string.

    Args:
        dt: Datetime para formatar
        format_str: Formato desejado

    Returns:
        str: Datetime formatado
    """
    return dt.strftime(format_str)


def parse_datetime(dt_str: str, format_str: str = "%Y-%m-%d %H:%M:%S") -> datetime:
    """
    Converte string para datetime.

    Args:
        dt_str: String para converter
        format_str: Formato da string

    Returns:
        datetime: Datetime parseado
    """
    return datetime.strptime(dt_str, format_str)


def days_ago(days: int) -> datetime:
    """
    Retorna datetime de N dias atrás.

    Args:
        days: Número de dias

    Returns:
        datetime: Data N dias atrás
    """
    return now() - timedelta(days=days)


def days_from_now(days: int) -> datetime:
    """
    Retorna datetime de N dias no futuro.

    Args:
        days: Número de dias

    Returns:
        datetime: Data N dias no futuro
    """
    return now() + timedelta(days=days)


def is_expired(dt: datetime, expiry_hours: int = 24) -> bool:
    """
    Verifica se uma data expirou.

    Args:
        dt: Data para verificar
        expiry_hours: Horas para expiração

    Returns:
        bool: True se expirado
    """
    expiry_time = dt + timedelta(hours=expiry_hours)
    return now() > expiry_time


def time_until_expiry(dt: datetime, expiry_hours: int = 24) -> Optional[timedelta]:
    """
    Calcula tempo até expiração.

    Args:
        dt: Data base
        expiry_hours: Horas para expiração

    Returns:
        timedelta: Tempo até expiração ou None se já expirado
    """
    expiry_time = dt + timedelta(hours=expiry_hours)
    time_left = expiry_time - now()
    return time_left if time_left.total_seconds() > 0 else None
