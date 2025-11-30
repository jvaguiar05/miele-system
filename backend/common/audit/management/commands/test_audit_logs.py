from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction
from apps.clients.models import Client, Address
from apps.perdcomps.models import PerDcomp
from common.audit.models import AuditLog
from common.audit.context import AuditContext
import uuid
from datetime import datetime, timedelta

User = get_user_model()


class Command(BaseCommand):
    help = "Testa o sistema de auditoria criando, atualizando e deletando dados"

    def add_arguments(self, parser):
        parser.add_argument(
            "--user-id",
            type=int,
            help="ID do usuário para simular as ações (opcional)",
        )
        parser.add_argument(
            "--cleanup",
            action="store_true",
            help="Remove dados de teste criados",
        )

    def handle(self, *args, **options):
        if options["cleanup"]:
            self._cleanup_test_data()
            return

        user = None
        if options["user_id"]:
            try:
                user = User.objects.get(id=options["user_id"])
                self.stdout.write(
                    self.style.SUCCESS(f"Usando usuário: {user.email} (ID: {user.id})")
                )
            except User.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(
                        f"Usuário com ID {options['user_id']} não encontrado"
                    )
                )
                return
        else:
            # Tentar obter um usuário ativo para o teste
            user = User.objects.filter(is_active=True).first()
            if user:
                self.stdout.write(
                    self.style.WARNING(
                        f"Usando usuário padrão: {user.email} (ID: {user.id})"
                    )
                )

        # Contar logs antes do teste
        logs_before = AuditLog.objects.count()
        self.stdout.write(f"Logs de auditoria antes do teste: {logs_before}")

        correlation_id = str(uuid.uuid4())

        # Usar contexto de auditoria para simular uma sessão
        with AuditContext(correlation_id=correlation_id, user=user):
            self._test_client_crud()
            self._test_perdcomp_crud()

        # Contar logs após o teste
        logs_after = AuditLog.objects.count()
        new_logs = logs_after - logs_before

        self.stdout.write(
            self.style.SUCCESS(f"Logs de auditoria após o teste: {logs_after}")
        )
        self.stdout.write(self.style.SUCCESS(f"Novos logs criados: {new_logs}"))

        # Mostrar os logs criados
        self._show_recent_logs(correlation_id)

    def _test_client_crud(self):
        """Testa operações CRUD em clientes."""
        self.stdout.write("\n=== Testando CRUD de Clientes ===")

        # CREATE
        self.stdout.write("1. Criando cliente...")
        address = Address.objects.create(
            logradouro="Rua Teste",
            numero="123",
            bairro="Centro",
            municipio="São Paulo",
            uf="SP",
            cep="01000-000",
        )

        client = Client.objects.create(
            razao_social="Empresa Teste Auditoria Ltda",
            cnpj="12.345.678/0001-99",
            email_comercial="teste@empresateste.com",
            telefone_comercial="(11) 99999-9999",
            address=address,
        )
        self.stdout.write(f"   Cliente criado: {client.id}")

        # UPDATE
        self.stdout.write("2. Atualizando cliente...")
        client.razao_social = "Empresa Teste Auditoria UPDATED Ltda"
        client.telefone_comercial = "(11) 88888-8888"
        client.save()
        self.stdout.write("   Cliente atualizado")

        # DELETE (soft delete)
        self.stdout.write("3. Excluindo cliente (soft delete)...")
        client.soft_delete()
        self.stdout.write("   Cliente excluído")

        # Store client ID for later cleanup
        self._test_client_id = client.id

    def _test_perdcomp_crud(self):
        """Testa operações CRUD em PER/DCOMPs."""
        self.stdout.write("\n=== Testando CRUD de PER/DCOMPs ===")

        # CREATE
        self.stdout.write("1. Criando PER/DCOMP...")
        perdcomp = PerDcomp.objects.create(
            client_id=1,  # Assumindo que existe pelo menos um cliente
            created_by_id=1,  # Assumindo que existe pelo menos um usuário
            cnpj="12.345.678/0001-99",
            numero="PERDCOMP-TEST-001",
            numero_perdcomp="TEST-001",
            data_vencimento=datetime.now() + timedelta(days=30),
            data_competencia=datetime.now(),
            tributo_pedido="IRPJ",
            competencia="2024",
            valor_pedido="1000.00",
            valor_compensado="0.00",
            valor_recebido="0.00",
            valor_saldo="1000.00",
            valor_selic="0.00",
        )
        self.stdout.write(f"   PER/DCOMP criado: {perdcomp.id}")

        # UPDATE
        self.stdout.write("2. Atualizando PER/DCOMP...")
        perdcomp.valor_compensado = "500.00"
        perdcomp.valor_saldo = "500.00"
        perdcomp.status = PerDcomp.Status.TRANSMITIDO
        perdcomp.save()
        self.stdout.write("   PER/DCOMP atualizado")

        # DELETE (soft delete)
        self.stdout.write("3. Excluindo PER/DCOMP (soft delete)...")
        perdcomp.soft_delete()
        self.stdout.write("   PER/DCOMP excluído")

        # Store perdcomp ID for later cleanup
        self._test_perdcomp_id = perdcomp.id

    def _show_recent_logs(self, correlation_id):
        """Mostra os logs recentes criados durante o teste."""
        self.stdout.write("\n=== Logs de Auditoria Criados ===")

        recent_logs = AuditLog.objects.filter(correlation_id=correlation_id).order_by(
            "timestamp"
        )

        if not recent_logs.exists():
            self.stdout.write(
                self.style.ERROR("❌ PROBLEMA: Nenhum log de auditoria foi criado!")
            )
            return

        for log in recent_logs:
            user_info = f"Usuário: {log.user.email if log.user else 'NULL'} (ID: {log.user.id if log.user else 'NULL'})"
            self.stdout.write(
                f"📝 {log.action} | {log.resource_type} | {user_info} | {log.timestamp}"
            )

            if log.metadata:
                self.stdout.write(f"   Metadata: {log.metadata}")

            if not log.user:
                self.stdout.write(
                    self.style.ERROR("   ❌ PROBLEMA: Usuário está NULL neste log!")
                )

    def _cleanup_test_data(self):
        """Remove dados de teste criados."""
        self.stdout.write("Removendo dados de teste...")

        # Remove logs de teste (opcional - pode querer manter para análise)
        # AuditLog.objects.filter(metadata__contains="test").delete()

        # Remove clientes de teste
        test_clients = Client.objects.filter(
            razao_social__icontains="Empresa Teste Auditoria"
        )
        count = test_clients.count()
        test_clients.delete()

        # Remove PER/DCOMPs de teste
        test_perdcomps = PerDcomp.objects.filter(numero__icontains="PERDCOMP-TEST")
        count += test_perdcomps.count()
        test_perdcomps.delete()

        self.stdout.write(self.style.SUCCESS(f"Removidos {count} registros de teste"))
