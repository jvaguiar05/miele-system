"""Safely reset all PER/DCOMP operational and documentary data."""

from __future__ import annotations

import json

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand, CommandError
from django.db import connections, transaction
from django.db.models.signals import post_delete
from django.utils import timezone

from apps.clients.models import Client, ClientContract, QuarterSnapshot
from apps.perdcomps.models import (
    DocumentaryCredit,
    DocumentaryEvent,
    DocumentCreditComponent,
    DocumentDebt,
    DocumentRelation,
    DocumentReview,
    DocumentUtilization,
    ImportedDocument,
    ImportedFile,
    ImportBatch,
    ManualImportIssue,
    PerDcomp,
)
from common.approvals.models import ApprovalRequest
from common.shared.models import Annotation, AttachedFile
from common.shared.signals import delete_file_from_drive


CONFIRMATION = "APAGAR-TODAS-AS-PERDCOMPS"


class Command(BaseCommand):
    help = (
        "Remove todas as PER/DCOMPs e seus dados documentais, preservando "
        "clientes, contratos, usuários, Selic, auditoria e arquivos do Drive."
    )

    def add_arguments(self, parser):
        parser.add_argument("--database", default="default")
        parser.add_argument(
            "--execute",
            action="store_true",
            help="Executa a limpeza. Sem esta opção, somente exibe a simulação.",
        )
        parser.add_argument("--confirm", default="")
        parser.add_argument("--expected-clients", type=int)
        parser.add_argument("--expected-perdcomps", type=int)

    def handle(self, *args, **options):
        database = options["database"]
        connection = connections[database]
        target = connection.settings_dict
        before = self._counts(database)

        self.stdout.write(
            self.style.WARNING(
                "Banco-alvo: "
                f"engine={target.get('ENGINE')} "
                f"host={target.get('HOST') or 'local'} "
                f"name={target.get('NAME')}"
            )
        )
        self.stdout.write(json.dumps(before, ensure_ascii=False, indent=2))

        if not options["execute"]:
            self.stdout.write(self.style.WARNING("SIMULAÇÃO: nenhum dado foi alterado."))
            self.stdout.write(
                "Para executar, repita com --execute "
                f"--confirm {CONFIRMATION} "
                f"--expected-clients {before['clients']} "
                f"--expected-perdcomps {before['perdcomps']}"
            )
            return

        if options["confirm"] != CONFIRMATION:
            raise CommandError(f"Confirmação inválida. Use exatamente: {CONFIRMATION}")
        if options["expected_clients"] is None or options["expected_perdcomps"] is None:
            raise CommandError(
                "Informe --expected-clients e --expected-perdcomps com os valores da simulação."
            )
        if options["expected_clients"] != before["clients"]:
            raise CommandError(
                f"Quantidade de clientes mudou: esperada={options['expected_clients']} atual={before['clients']}."
            )
        if options["expected_perdcomps"] != before["perdcomps"]:
            raise CommandError(
                "Quantidade de PER/DCOMPs mudou: "
                f"esperada={options['expected_perdcomps']} atual={before['perdcomps']}."
            )

        preserved = {
            "clients": before["clients"],
            "contracts": before["contracts"],
            "client_annotations": before["client_annotations"],
            "client_attachments": before["client_attachments"],
        }

        # Legacy PER/DCOMP attachments use a post-delete signal that removes the
        # physical Drive file. During a reset we preserve those files as an
        # external archive and remove only their obsolete database references.
        post_delete.disconnect(delete_file_from_drive, sender=AttachedFile)
        try:
            with transaction.atomic(using=database):
                self._purge(database)
                after = self._counts(database)
                actual_preserved = {
                    "clients": after["clients"],
                    "contracts": after["contracts"],
                    "client_annotations": after["client_annotations"],
                    "client_attachments": after["client_attachments"],
                }
                if actual_preserved != preserved:
                    raise CommandError(
                        "A validação de preservação falhou; toda a transação foi revertida. "
                        f"Antes={preserved} Depois={actual_preserved}"
                    )
                remaining = {
                    key: value
                    for key, value in after.items()
                    if key not in {
                        "clients",
                        "contracts",
                        "client_annotations",
                        "client_attachments",
                        "audit_logs",
                    }
                    and value
                }
                if remaining:
                    raise CommandError(
                        "Ainda existem dados de PER/DCOMP; toda a transação foi revertida: "
                        f"{remaining}"
                    )
        finally:
            post_delete.connect(delete_file_from_drive, sender=AttachedFile)

        self.stdout.write(self.style.SUCCESS("Limpeza concluída com sucesso."))
        self.stdout.write(json.dumps(after, ensure_ascii=False, indent=2))
        self.stdout.write(
            self.style.WARNING(
                "Os arquivos físicos do Google Drive foram preservados. "
                "Mantenha a pasta antiga arquivada e use uma pasta nova no sistema."
            )
        )

    def _counts(self, database):
        perdcomp_type = ContentType.objects.db_manager(database).get_for_model(PerDcomp)
        client_type = ContentType.objects.db_manager(database).get_for_model(Client)
        from common.audit.models import AuditLog

        return {
            "clients": Client.objects.using(database).count(),
            "contracts": ClientContract.objects.using(database).count(),
            "perdcomps": PerDcomp.objects.using(database).count(),
            "import_batches": ImportBatch.objects.using(database).count(),
            "documentary_credits": DocumentaryCredit.objects.using(database).count(),
            "imported_documents": ImportedDocument.objects.using(database).count(),
            "imported_files": ImportedFile.objects.using(database).count(),
            "manual_issues": ManualImportIssue.objects.using(database).count(),
            "relations": DocumentRelation.objects.using(database).count(),
            "debts": DocumentDebt.objects.using(database).count(),
            "credit_components": DocumentCreditComponent.objects.using(database).count(),
            "utilizations": DocumentUtilization.objects.using(database).count(),
            "reviews": DocumentReview.objects.using(database).count(),
            "events": DocumentaryEvent.objects.using(database).count(),
            "perdcomp_annotations": Annotation.objects.using(database).filter(content_type=perdcomp_type).count(),
            "perdcomp_attachments": AttachedFile.objects.using(database).filter(content_type=perdcomp_type).count(),
            "quarter_snapshots": QuarterSnapshot.objects.using(database).count(),
            "pending_perdcomp_approvals": ApprovalRequest.objects.using(database).filter(
                resource_type__iexact="perdcomps.PerDcomp", status=ApprovalRequest.ApprovalStatus.PENDING
            ).count(),
            "client_annotations": Annotation.objects.using(database).filter(content_type=client_type).count(),
            "client_attachments": AttachedFile.objects.using(database).filter(content_type=client_type).count(),
            "audit_logs": AuditLog.objects.using(database).count(),
        }

    def _purge(self, database):
        perdcomp_type = ContentType.objects.db_manager(database).get_for_model(PerDcomp)

        ApprovalRequest.objects.using(database).filter(
            resource_type__iexact="perdcomps.PerDcomp",
            status=ApprovalRequest.ApprovalStatus.PENDING,
        ).update(
            status=ApprovalRequest.ApprovalStatus.CANCELLED,
            updated_at=timezone.now(),
            approval_notes="Cancelada durante reinicialização controlada das PER/DCOMPs.",
        )
        QuarterSnapshot.objects.using(database).all().delete()
        Annotation.objects.using(database).filter(content_type=perdcomp_type).delete()
        AttachedFile.objects.using(database).filter(content_type=perdcomp_type).delete()

        DocumentaryEvent.objects.using(database).update(parent=None)
        ImportedDocument.objects.using(database).update(superseded_by=None)
        PerDcomp.objects.using(database).update(superseded_by=None)

        DocumentReview.objects.using(database).all().delete()
        DocumentRelation.objects.using(database).all().delete()
        DocumentDebt.objects.using(database).all().delete()
        DocumentCreditComponent.objects.using(database).all().delete()
        DocumentUtilization.objects.using(database).all().delete()
        DocumentaryEvent.objects.using(database).all().delete()
        ImportedFile.objects.using(database).all().delete()
        ManualImportIssue.objects.using(database).all().delete()
        ImportedDocument.objects.using(database).all().delete()
        DocumentaryCredit.objects.using(database).all().delete()
        ImportBatch.objects.using(database).all().delete()
        PerDcomp.objects.using(database).all().delete()
