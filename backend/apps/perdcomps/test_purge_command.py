from datetime import date
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.clients.models import Client, ClientContract, QuarterSnapshot
from common.approvals.models import ApprovalRequest
from common.shared.models import Annotation, AttachedFile
from .document_models import (
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
)
from .management.commands.purge_perdcomps import CONFIRMATION
from .models import PerDcomp


class PurgePerdcompsCommandTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="purge-admin",
            email="purge@example.test",
            role="admin",
            approval_status="approved",
        )
        self.client = Client.objects.create(razao_social="Cliente preservado", cnpj="12.345.678/0001-90")
        ClientContract.objects.create(
            client=self.client,
            percentage="5.0000",
            starts_on=date(2026, 1, 1),
            created_by=self.user,
        )
        self.old = self._perdcomp("11111.11111.111111.1.1.11-1111")
        self.current = self._perdcomp("22222.22222.222222.1.1.11-2222")
        self.old.superseded_by = self.current
        self.old.save(update_fields=["superseded_by"])

        batch = ImportBatch.objects.create(
            client=self.client,
            fingerprint="a" * 64,
            created_by=self.user,
            summary={},
        )
        credit = DocumentaryCredit.objects.create(
            client=self.client,
            origin_protocol="111111111111111111111111",
        )
        first = ImportedDocument.objects.create(
            client=self.client,
            cnpj="12345678000190",
            protocol="111111111111111111111111",
            protocol_original="11111.11111.111111.1.1.11-1111",
            credit=credit,
            legacy_document=self.old,
            modality="compensacao",
            revision_kind="original",
            completeness="complete",
            data={},
        )
        second = ImportedDocument.objects.create(
            client=self.client,
            cnpj="12345678000190",
            protocol="222222222222222222222222",
            protocol_original="22222.22222.222222.1.1.11-2222",
            credit=credit,
            legacy_document=self.current,
            modality="compensacao",
            revision_kind="retificadora",
            completeness="complete",
            data={},
        )
        first.superseded_by = second
        first.save(update_fields=["superseded_by"])
        ImportedFile.objects.create(
            client=self.client,
            document=first,
            batch=batch,
            sha256="b" * 64,
            original_name="documento.pdf",
            kind="demonstrative",
            pages=1,
            drive_file_id="documentary-drive-file",
            original_content=b"pdf",
            parser_version="test",
            extraction={},
        )
        ManualImportIssue.objects.create(
            client=self.client,
            batch=batch,
            sha256="c" * 64,
            original_name="pendente.pdf",
            original_content=b"pdf",
            issues=["teste"],
            operational_document=self.current,
            created_by=self.user,
        )
        DocumentRelation.objects.create(
            source=second,
            kind="retifies",
            target_protocol=first.protocol,
            target=first,
            legacy_target=self.old,
        )
        DocumentDebt.objects.create(document=second, sequence=1, principal="10.00", total="10.00", data={})
        DocumentCreditComponent.objects.create(document=first, sequence=1, assessed="100.00", data={})
        DocumentUtilization.objects.create(document=second, declared="10.00")
        DocumentReview.objects.create(document=second, batch=batch, reviewer=self.user, changes=[], reason="Teste")
        parent = DocumentaryEvent.objects.create(document=first, kind="decision", event_key="one", data={})
        DocumentaryEvent.objects.create(document=second, kind="calculation", event_key="two", parent=parent, data={})

        QuarterSnapshot.objects.create(
            year=2026,
            quarter=1,
            kind="position",
            captured_by="Teste",
            payload={},
        )
        ApprovalRequest.objects.create(
            subject="Alterar PER/DCOMP",
            action=ApprovalRequest.ApprovalAction.UPDATE,
            resource_type="perdcomps.PerDcomp",
            resource_id=str(self.current.pk),
            payload_diff={},
            reason="Teste",
            requested_by=self.user,
        )

        perdcomp_type = ContentType.objects.get_for_model(PerDcomp)
        client_type = ContentType.objects.get_for_model(Client)
        Annotation.objects.create(content_type=perdcomp_type, object_id=self.old.pk, user_id=self.user.pk, content={"text": "apagar"})
        Annotation.objects.create(content_type=client_type, object_id=self.client.pk, user_id=self.user.pk, content={"text": "preservar"})
        AttachedFile.objects.create(
            content_type=perdcomp_type,
            object_id=self.old.pk,
            file_type="perdcomp",
            file_name="perdcomp.pdf",
            file_size=3,
            mime_type="application/pdf",
            drive_file_id="legacy-perdcomp-drive-file",
            uploaded_by_id=self.user.pk,
        )
        AttachedFile.objects.create(
            content_type=client_type,
            object_id=self.client.pk,
            file_type="contrato",
            file_name="cliente.pdf",
            file_size=3,
            mime_type="application/pdf",
            drive_file_id="client-drive-file",
            uploaded_by_id=self.user.pk,
        )

    def _perdcomp(self, protocol):
        return PerDcomp.objects.create(
            client_id=self.client.pk,
            created_by_id=self.user.pk,
            cnpj=self.client.cnpj,
            numero_perdcomp=protocol,
            tributo_pedido="COFINS",
            valor_pedido="100.00",
        )

    def test_default_is_dry_run(self):
        output = StringIO()
        call_command("purge_perdcomps", stdout=output)
        self.assertIn("SIMULAÇÃO", output.getvalue())
        self.assertEqual(PerDcomp.objects.count(), 2)
        self.assertEqual(ImportedDocument.objects.count(), 2)

    def test_wrong_expected_count_aborts_without_changes(self):
        with self.assertRaises(CommandError):
            call_command(
                "purge_perdcomps",
                execute=True,
                confirm=CONFIRMATION,
                expected_clients=999,
                expected_perdcomps=2,
                stdout=StringIO(),
            )
        self.assertEqual(Client.objects.count(), 1)
        self.assertEqual(PerDcomp.objects.count(), 2)

    @patch("common.shared.signals.drive_service.delete_file")
    def test_execute_clears_perdcomps_and_preserves_client_data_and_drive(self, delete_drive):
        call_command(
            "purge_perdcomps",
            execute=True,
            confirm=CONFIRMATION,
            expected_clients=1,
            expected_perdcomps=2,
            stdout=StringIO(),
        )

        self.assertEqual(Client.objects.count(), 1)
        self.assertEqual(ClientContract.objects.count(), 1)
        self.assertEqual(PerDcomp.objects.count(), 0)
        self.assertEqual(ImportedDocument.objects.count(), 0)
        self.assertEqual(ImportedFile.objects.count(), 0)
        self.assertEqual(ManualImportIssue.objects.count(), 0)
        self.assertEqual(QuarterSnapshot.objects.count(), 0)
        client_type = ContentType.objects.get_for_model(Client)
        self.assertEqual(Annotation.objects.filter(content_type=client_type).count(), 1)
        self.assertEqual(AttachedFile.objects.filter(content_type=client_type).count(), 1)
        approval = ApprovalRequest.objects.get()
        self.assertEqual(approval.status, ApprovalRequest.ApprovalStatus.CANCELLED)
        delete_drive.assert_not_called()
