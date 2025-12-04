from django.core.management.base import BaseCommand
from apps.clients.models import Client
from apps.clients.serializers import ClientSerializer
from common.audit.models import AuditLog
from django.contrib.auth import get_user_model
from datetime import datetime

User = get_user_model()


class Command(BaseCommand):
    help = "Simula uma atualização via serializer como o frontend faz"

    def handle(self, *args, **options):
        self.stdout.write("=== Simulando Update via Serializer (como Frontend) ===")

        # Encontrar um cliente
        client = Client.objects.first()
        if not client:
            self.stdout.write("❌ Nenhum cliente encontrado")
            return

        self.stdout.write(f"✅ Cliente encontrado: {client.razao_social}")
        self.stdout.write(
            f"   Data contratual original: {client.ultima_alteracao_contratual}"
        )

        # Contar logs existentes
        existing_logs = AuditLog.objects.filter(
            content_type__model="client", object_id=client.pk
        ).count()
        self.stdout.write(f"   Logs existentes: {existing_logs}")

        # Simular dados de update do frontend (apenas email comercial)
        update_data = {"email_comercial": "novo@empresa.com"}

        self.stdout.write(
            f"🔄 Atualizando apenas email_comercial para: {update_data['email_comercial']}"
        )
        self.stdout.write("   (ultima_alteracao_contratual NÃO deve aparecer nos logs)")

        # Usar o serializer como o frontend faz
        serializer = ClientSerializer(instance=client, data=update_data, partial=True)
        if serializer.is_valid():
            updated_client = serializer.save()
            self.stdout.write("✅ Cliente atualizado via serializer")

            # Verificar novos logs
            new_logs_count = AuditLog.objects.filter(
                content_type__model="client", object_id=client.pk
            ).count()

            self.stdout.write(f"   Total de logs após update: {new_logs_count}")

            if new_logs_count > existing_logs:
                # Pegar logs mais recentes
                recent_logs = AuditLog.objects.filter(
                    content_type__model="client", object_id=client.pk
                ).order_by("-timestamp")[:3]

                self.stdout.write("📋 Logs criados:")
                for i, log in enumerate(recent_logs, 1):
                    self.stdout.write(f"   Log {i}:")
                    self.stdout.write(f"     Action: {log.action}")
                    self.stdout.write(f"     Timestamp: {log.timestamp}")
                    if log.new_data:
                        self.stdout.write(
                            f"     Campos alterados: {list(log.new_data.keys())}"
                        )
                        for field, value in log.new_data.items():
                            old_value = (
                                log.old_data.get(field, "N/A")
                                if log.old_data
                                else "N/A"
                            )
                            self.stdout.write(
                                f"       {field}: '{old_value}' -> '{value}'"
                            )
                    self.stdout.write("")
            else:
                self.stdout.write("❓ Nenhum log novo foi criado")

            # Reverter mudança
            client.email_comercial = "comercial@empresa.com"  # valor original
            client.save()
            self.stdout.write("✅ Mudança revertida")

        else:
            self.stdout.write(f"❌ Erro na serialização: {serializer.errors}")

        self.stdout.write("=== Fim da Simulação ===")
