from django.core.management.base import BaseCommand
from apps.clients.models import Client
from common.audit.services import AuditService
from common.audit.models import AuditLog
from datetime import date, datetime
import traceback


class Command(BaseCommand):
    help = "Testa o sistema de auditoria em detalhes"

    def handle(self, *args, **options):
        self.stdout.write("=== Teste Detalhado de Auditoria ===")

        # Verificar se o modelo Client tem auditoria habilitada
        client_audit = getattr(Client, "__audit__", "Não definido")
        self.stdout.write(f"Cliente.__audit__ = {client_audit}")

        # Encontrar um cliente
        client = Client.objects.first()
        if not client:
            self.stdout.write("❌ Nenhum cliente encontrado")
            return

        self.stdout.write(f"✅ Cliente encontrado: {client.razao_social}")
        self.stdout.write(f"   ID: {client.pk}")
        self.stdout.write(f"   Data contratual: {client.ultima_alteracao_contratual}")

        # Verificar instância de auditoria
        instance_audit = getattr(client, "__audit__", "Não definido")
        self.stdout.write(f"   Instância.__audit__ = {instance_audit}")

        # Verificar logs existentes
        existing_logs = AuditLog.objects.filter(
            content_type__model="client", object_id=client.pk
        ).count()
        self.stdout.write(f"   Logs existentes: {existing_logs}")

        try:
            # Capturar dados antigos
            old_data = AuditService._serialize_object(client)
            self.stdout.write(f"✅ Dados antigos capturados: {len(old_data)} campos")

            # Mostrar alguns campos importantes
            important_fields = [
                "razao_social",
                "ultima_alteracao_contratual",
                "updated_at",
            ]
            for field in important_fields:
                if field in old_data:
                    self.stdout.write(
                        f"   {field}: {old_data[field]} ({type(old_data[field])})"
                    )

            # Fazer uma mudança simples
            original_name = client.razao_social
            client.razao_social = f"{original_name} (Test Update)"

            self.stdout.write(f"🔄 Alterando nome para: {client.razao_social}")

            # Verificar se os signals estão conectados
            from django.db.models.signals import post_save, pre_save
            from common.audit.signals import capture_pre_save_data, audit_post_save

            pre_save_receivers = pre_save._live_receivers(sender=Client)
            post_save_receivers = post_save._live_receivers(sender=Client)

            self.stdout.write(f"   Pre-save receivers: {len(pre_save_receivers)}")
            self.stdout.write(f"   Post-save receivers: {len(post_save_receivers)}")

            # Verificar se nossos receivers estão lá
            pre_save_connected = any(
                str(receiver) == str((None, capture_pre_save_data))
                for receiver in pre_save_receivers
            )
            post_save_connected = any(
                str(receiver) == str((None, audit_post_save))
                for receiver in post_save_receivers
            )

            self.stdout.write(
                f"   Nosso pre-save signal conectado: {pre_save_connected}"
            )
            self.stdout.write(
                f"   Nosso post-save signal conectado: {post_save_connected}"
            )

            # Adicionar um debug temporário no cliente
            client._debug_audit = True

            # Salvar
            client.save()
            self.stdout.write("✅ Cliente salvo")

            # Verificar se _audit_old_data foi capturado
            has_old_data = hasattr(client, "_audit_old_data")
            self.stdout.write(f"   _audit_old_data capturado: {has_old_data}")
            if has_old_data:
                self.stdout.write(
                    f"   Dados antigos: {len(client._audit_old_data) if client._audit_old_data else 0} campos"
                )  # Verificar se novos logs foram criados
            new_logs_count = AuditLog.objects.filter(
                content_type__model="client", object_id=client.pk
            ).count()

            self.stdout.write(f"   Total de logs após save: {new_logs_count}")

            if new_logs_count > existing_logs:
                # Pegar o log mais recente
                latest_log = (
                    AuditLog.objects.filter(
                        content_type__model="client", object_id=client.pk
                    )
                    .order_by("-timestamp")
                    .first()
                )

                self.stdout.write("✅ Novo log criado!")
                self.stdout.write(f"   Action: {latest_log.action}")
                self.stdout.write(f"   User: {latest_log.user}")
                self.stdout.write(f"   Timestamp: {latest_log.timestamp}")
                self.stdout.write(f"   Old data fields: {len(latest_log.old_data)}")
                self.stdout.write(f"   New data fields: {len(latest_log.new_data)}")
                self.stdout.write(f"   Metadata: {latest_log.metadata}")

                # Mostrar campos que mudaram
                if latest_log.old_data and latest_log.new_data:
                    self.stdout.write("   Campos alterados:")
                    for field in latest_log.new_data:
                        old_val = latest_log.old_data.get(field, "N/A")
                        new_val = latest_log.new_data[field]
                        self.stdout.write(f"     {field}: '{old_val}' -> '{new_val}'")
            else:
                self.stdout.write("❌ Nenhum log novo foi criado!")

            # Reverter
            client.razao_social = original_name
            client.save()
            self.stdout.write("✅ Mudança revertida")

        except Exception as e:
            self.stdout.write(f"❌ Erro: {e}")
            self.stdout.write(traceback.format_exc())

        self.stdout.write("=== Fim do Teste ===")
