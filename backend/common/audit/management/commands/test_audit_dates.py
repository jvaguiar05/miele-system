#!/usr/bin/env python
"""
Script para testar se a correção dos logs de auditoria funciona corretamente
para campos de data/datetime.
"""
from django.core.management.base import BaseCommand
from apps.clients.models import Client
from common.audit.services import AuditService
from django.contrib.auth import get_user_model
from datetime import date, datetime

User = get_user_model()


class Command(BaseCommand):
    help = "Testa a auditoria de campos de data/datetime"

    def handle(self, *args, **options):
        test_date_comparison()
        test_client_update()


def test_date_comparison():
    """Testa se a comparação de datas funciona corretamente."""
    print("=== Teste de Comparação de Datas ===")

    # Test cases
    test_cases = [
        # (old_value, new_value, should_be_different, description)
        (None, None, False, "Ambos None"),
        (date(2024, 1, 1), date(2024, 1, 1), False, "Mesma data"),
        (date(2024, 1, 1), date(2024, 1, 2), True, "Datas diferentes"),
        ("2024-01-01", date(2024, 1, 1), False, "String vs Date (mesma data)"),
        ("2024-01-01T00:00:00", date(2024, 1, 1), False, "Datetime midnight vs Date"),
        ("2024-01-01T10:00:00", date(2024, 1, 1), True, "Datetime com tempo vs Date"),
        (
            datetime(2024, 1, 1, 0, 0, 0),
            date(2024, 1, 1),
            False,
            "Datetime midnight vs Date",
        ),
        (
            datetime(2024, 1, 1, 10, 0, 0),
            date(2024, 1, 1),
            True,
            "Datetime com tempo vs Date",
        ),
    ]

    for old_val, new_val, expected, description in test_cases:
        result = AuditService._values_are_different("test_field", old_val, new_val)
        status = "✓" if result == expected else "✗"
        print(
            f"{status} {description}: {old_val} vs {new_val} -> Different: {result} (expected: {expected})"
        )


def test_client_update():
    """Testa uma atualização real de cliente."""
    print("\n=== Teste de Atualização de Cliente ===")

    try:
        # Encontrar qualquer cliente de teste
        client = Client.objects.first()
        if not client:
            print("Nenhum cliente encontrado para teste")
            return

        print(f"Cliente encontrado: {client.razao_social}")
        print(
            f"Data atual ultima_alteracao_contratual: {client.ultima_alteracao_contratual}"
        )

        # Fazer uma atualização que NÃO muda a data
        old_name = client.razao_social
        client.razao_social = f"{old_name} (Updated)"

        print(
            f"Alterando apenas a razão social de '{old_name}' para '{client.razao_social}'"
        )
        print(
            "A data ultima_alteracao_contratual NÃO deve aparecer nos logs se não foi alterada..."
        )

        # Salvar e verificar os logs
        client.save()

        print(
            "Cliente salvo! Verifique os logs de auditoria para ver se a data aparece."
        )

        # Reverter a mudança
        client.razao_social = old_name
        client.save()

    except Exception as e:
        print(f"Erro no teste: {e}")


if __name__ == "__main__":
    test_date_comparison()
    test_client_update()
    print("\n=== Fim dos Testes ===")
