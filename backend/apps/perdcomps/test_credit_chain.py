from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.clients.models import Client
from .document_models import (
    DocumentaryCredit,
    DocumentRelation,
    DocumentUtilization,
    ImportBatch,
    ImportedDocument,
    ImportedFile,
)
from .models import PerDcomp


class CreditChainReportTests(TestCase):
    def setUp(self):
        self.client_record = Client.objects.create(
            razao_social="Cliente cadeia",
            cnpj="19.818.301/0001-55",
        )
        self.employee = get_user_model().objects.create_user(
            username="chain-employee",
            email="chain-employee@example.test",
            role="employee",
            approval_status="approved",
        )
        self.guest = get_user_model().objects.create_user(
            username="chain-guest",
            email="chain-guest@example.test",
            role="guest",
            approval_status="approved",
        )
        self.url = f"/api/v1/clients/{self.client_record.public_id}/perdcomp-imports/credit-chain/"

    def document(self, protocol, *, credit=None, values=None, version_status="current"):
        return ImportedDocument.objects.create(
            client=self.client_record,
            cnpj="19818301000155",
            protocol=protocol,
            protocol_original=protocol,
            credit=credit,
            modality="declaracao_compensacao",
            revision_kind="original",
            completeness="complete",
            version_status=version_status,
            data={
                "protocol": protocol,
                "transmitted_on": "2026-04-17",
                "requested": None,
                "used": None,
                "declared_balance": None,
                **(values or {}),
            },
        )

    def get_report(self, user=None):
        api = APIClient()
        api.force_authenticate(user or self.employee)
        return api.get(self.url)

    def test_report_exposes_declared_values_without_calculating_or_mutating(self):
        origin_protocol = "27053.67673.160426.1.1.19-3690"
        usage_protocol = "08084.82022.170426.1.3.19-1700"
        credit = DocumentaryCredit.objects.create(
            client=self.client_record,
            origin_protocol=origin_protocol.replace(".", "").replace("-", ""),
        )
        origin = self.document(credit.origin_protocol, credit=credit, values={"requested": "1000.00"})
        usage = self.document(
            usage_protocol.replace(".", "").replace("-", ""),
            credit=credit,
            values={"used": "100.00", "declared_balance": "900.00"},
        )
        DocumentUtilization.objects.create(document=usage, declared="100.00")
        DocumentRelation.objects.create(
            source=usage,
            kind="credit_origin",
            target_protocol=origin.protocol,
            target=origin,
        )

        response = self.get_report()

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["calculation"]["enabled"])
        self.assertEqual(response.data["calculation"]["status"], "pending_business_rules")
        self.assertEqual(response.data["counts"]["chains"], 1)
        chain = response.data["chains"][0]
        self.assertEqual(chain["status"], "documented")
        usage_item = next(item for item in chain["documents"] if item["protocol"] == usage.protocol)
        self.assertEqual(usage_item["documentary_values"]["used"], "100.00")
        self.assertEqual(usage_item["documentary_values"]["declared_balance"], "900.00")
        self.assertIsNone(usage_item["operational_values"])
        self.assertEqual(ImportedDocument.objects.get(pk=usage.pk).data["declared_balance"], "900.00")

    def test_missing_values_remain_null_and_pending_origin_is_explained(self):
        usage = self.document("080848202217042613191700")
        DocumentRelation.objects.create(
            source=usage,
            kind="credit_origin",
            target_protocol="270536767316042611193690",
        )

        response = self.get_report()

        self.assertEqual(response.status_code, 200)
        chain = response.data["chains"][0]
        self.assertEqual(chain["status"], "attention")
        self.assertEqual(response.data["counts"]["pending_references"], 1)
        self.assertIsNone(chain["documents"][0]["documentary_values"]["requested"])
        self.assertIsNone(chain["documents"][0]["documentary_values"]["used"])
        self.assertTrue(any("origem" in issue.lower() for issue in chain["issues"]))

    def test_parallel_rectifiers_mark_chain_as_ambiguous(self):
        origin = self.document("270536767316042611193690")
        credit = DocumentaryCredit.objects.create(
            client=self.client_record,
            origin_protocol=origin.protocol,
        )
        origin.credit = credit
        origin.save(update_fields=["credit"])
        first = self.document("080848202217042613191700", credit=credit)
        second = self.document("080858202218042613191701", credit=credit)
        for source in (first, second):
            DocumentRelation.objects.create(
                source=source,
                kind="rectifies",
                target_protocol=origin.protocol,
                target=origin,
            )

        response = self.get_report()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["counts"]["ambiguous_chains"], 1)
        chain = response.data["chains"][0]
        self.assertEqual(chain["status"], "ambiguous")
        self.assertTrue(any("mais de uma retificadora" in issue.lower() for issue in chain["issues"]))
        self.assertFalse(response.data["calculation"]["enabled"])

    def test_approved_guest_can_consult_but_endpoint_is_read_only(self):
        self.document("270536767316042611193690")

        get_response = self.get_report(self.guest)
        api = APIClient()
        api.force_authenticate(self.employee)
        post_response = api.post(self.url, {})

        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(post_response.status_code, 405)

    def test_operational_detail_exposes_import_fields_chain_and_download_metadata(self):
        protocol = "270536767316042611193690"
        operational = PerDcomp.objects.create(
            client_id=self.client_record.pk,
            created_by_id=self.employee.pk,
            cnpj=self.client_record.cnpj,
            numero_perdcomp=protocol,
            tributo_pedido="COFINS",
            valor_pedido="1000.00",
        )
        credit = DocumentaryCredit.objects.create(
            client=self.client_record,
            origin_protocol=protocol,
        )
        imported = self.document(
            protocol,
            credit=credit,
            values={"requested": "1000.00", "quarter": 1, "name": "Cliente cadeia"},
        )
        imported.legacy_document = operational
        imported.save(update_fields=["legacy_document"])
        batch = ImportBatch.objects.create(
            client=self.client_record,
            fingerprint="a" * 64,
            created_by=self.employee,
        )
        imported_file = ImportedFile.objects.create(
            client=self.client_record,
            document=imported,
            batch=batch,
            sha256="b" * 64,
            original_name="PER COFINS.pdf",
            kind="demonstrative",
            pages=3,
            original_content=b"%PDF-test",
            parser_version="test",
            extraction={"text_source": "ocr", "ocr": {"confidence": 99}, "evidence": {}},
        )
        api = APIClient()
        api.force_authenticate(self.employee)

        response = api.get(f"/api/v1/perdcomps/{operational.public_id}/documentary/")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["has_import"])
        self.assertEqual(response.data["client_id"], str(self.client_record.public_id))
        self.assertEqual(response.data["documents"][0]["fields"]["requested"], "1000.00")
        self.assertEqual(response.data["documents"][0]["files"][0]["id"], str(imported_file.public_id))
        self.assertTrue(response.data["documents"][0]["files"][0]["available"])
        self.assertNotIn("original_content", response.data["documents"][0]["files"][0])
        self.assertEqual(response.data["chain"]["origin_protocol"], protocol)
        self.assertFalse(response.data["calculation"]["enabled"])

    def test_manual_operational_detail_explains_absence_of_import(self):
        operational = PerDcomp.objects.create(
            client_id=self.client_record.pk,
            created_by_id=self.employee.pk,
            cnpj=self.client_record.cnpj,
            numero_perdcomp="MANUAL-1",
            tributo_pedido="COFINS",
            valor_pedido="100.00",
        )
        api = APIClient()
        api.force_authenticate(self.guest)

        response = api.get(f"/api/v1/perdcomps/{operational.public_id}/documentary/")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["has_import"])
        self.assertEqual(response.data["documents"], [])
        self.assertIn("cadastrada manualmente", response.data["message"])
