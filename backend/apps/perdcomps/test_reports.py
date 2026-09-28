from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.clients.models import Client
from apps.clients.dashboard_operations import build_operations_data
from common.audit.services import AuditService
from .models import PerDcomp


class ReportTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="reports", role="admin", approval_status="approved", is_staff=True)
        self.api = APIClient()
        self.api.force_authenticate(self.user)
        self.company = Client.objects.create(razao_social="Empresa Teste A", cnpj="12345678000100", is_active=True)
        self.other = Client.objects.create(razao_social="Empresa Teste B", cnpj="98765432000100", is_active=True)
        self.url = reverse("status-report")

    def record(self, **kwargs):
        values = dict(client_id=self.company.id, created_by_id=self.user.id, cnpj=self.company.cnpj,
                      numero_perdcomp="TESTE", status="TRANSMITIDO", tributo_pedido="COFINS",
                      data_transmissao=date(2025, 9, 24), data_vencimento=date(2026, 9, 24),
                      valor_pedido="100.10", valor_saldo="40.05")
        return PerDcomp.objects.create(**(values | kwargs))

    def test_scopes_match_dashboard_and_all_statuses_are_included(self):
        for status, _ in PerDcomp.Status.choices:
            self.record(status=status)
        self.record(is_active=False)
        self.record(client_id=self.other.id)
        self.other.is_active = False
        self.other.save()
        with patch("django.utils.timezone.localdate", return_value=date(2026, 9, 24)):
            dashboard = build_operations_data()
            all_rows = self.api.get(self.url).data
            self.assertEqual(all_rows["count"], dashboard["processes"])
            transmitted = self.api.get(self.url, {"scope": "transmitted"}).data
            self.assertEqual(transmitted["summary"]["amount"], dashboard["transmitted_amount"])
            self.assertEqual(transmitted["count"], dashboard["transmitted_count"])
            opened = self.api.get(self.url, {"scope": "open"}).data
            self.assertEqual(opened["summary"]["balance"], dashboard["balance"])
            for status, _ in PerDcomp.Status.choices:
                self.assertEqual(self.api.get(self.url, {"status": status}).data["count"], 1)

    def test_combined_filters_dates_empty_and_invalid(self):
        self.record()
        self.record(client_id=self.other.id, tributo_pedido="IRPJ", data_transmissao=date(2025, 1, 1))
        result = self.api.get(self.url, {"client_id": str(self.company.public_id), "client": "Teste A", "status": "TRANSMITIDO", "tax": "COF", "start": "2025-09-24", "end": "2025-09-24"})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data["count"], 1)
        self.assertEqual(self.api.get(self.url, {"date_field": "data_vencimento", "start": "2026-09-24", "end": "2026-09-24"}).data["count"], 2)
        self.assertEqual(self.api.get(self.url, {"client": "ausente"}).data["count"], 0)
        for params in [{"status": "INVALID"}, {"date_field": "password"}, {"start": "2026-12-01", "end": "2026-01-01"}, {"client_id": "invalid"}]:
            self.assertEqual(self.api.get(self.url, params).status_code, 400)

    def test_multiple_clients_filter(self):
        third = Client.objects.create(razao_social="Empresa Teste C", cnpj="11111111000111", is_active=True)
        self.record(numero_perdcomp="A")
        self.record(client_id=self.other.id, cnpj=self.other.cnpj, numero_perdcomp="B")
        self.record(client_id=third.id, cnpj=third.cnpj, numero_perdcomp="C")
        selected = f"{self.company.public_id},{self.other.public_id}"
        result = self.api.get(self.url, {"client_ids": selected})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data["count"], 2)
        self.assertEqual({item["id"] for item in result.data["selected_clients"]}, {str(self.company.public_id), str(self.other.public_id)})
        self.assertEqual(self.api.get(self.url, {"client_ids": "invalid"}).status_code, 400)

    def test_pagination_export_all_rows_and_missing_money(self):
        for i in range(51):
            self.record(numero_perdcomp=f"=TESTE-{i}", valor_saldo="")
        first = self.api.get(self.url)
        self.assertEqual(first.data["count"], 51)
        self.assertEqual(len(first.data["results"]), 50)
        self.assertEqual(first.data["summary"]["amount"], "5105.10")
        self.assertEqual(first.data["summary"]["missing_values"], 51)
        self.assertEqual(len(self.api.get(self.url, {"page": 2}).data["results"]), 1)
        export = self.api.get(self.url, {"export": "csv", "page": 2})
        self.assertEqual(len(export.content.decode("utf-8-sig").splitlines()), 52)
        self.assertIn("'=TESTE-50", export.content.decode("utf-8-sig"))

    def test_history_filters_resource_preserves_reasons_and_is_readonly(self):
        record = self.record()
        unrelated = self.record()
        for obj, reason in [(record, "Primeira justificativa"), (record, "Segunda justificativa"), (unrelated, "Outro processo")]:
            AuditService.log_action("CUSTOM", obj, user=self.user,
                old_data={"data_vencimento": "2026-09-24"}, new_data={"data_vencimento": "2026-10-01"},
                metadata={"type": "due_date_override", "reason": reason})
        url = reverse("deadline-history", args=[record.public_id])
        result = self.api.get(url)
        reasons = [r["reason"] for r in result.data["results"] if r["reason"]]
        self.assertEqual(reasons, ["Segunda justificativa", "Primeira justificativa"])
        self.assertEqual(result.data["results"][0]["user"], "reports")
        self.assertEqual(self.api.post(url, {}).status_code, 405)

    def test_permissions(self):
        record = self.record()
        history = reverse("deadline-history", args=[record.public_id])
        self.api.force_authenticate(None)
        self.assertEqual(self.api.get(self.url).status_code, 401)
        self.assertEqual(self.api.get(history).status_code, 401)
        self.user.role = "guest"
        self.user.save()
        self.api.force_authenticate(self.user)
        self.assertEqual(self.api.get(self.url).status_code, 403)
        self.assertEqual(self.api.get(history).status_code, 403)
        self.user.role = "employee"
        self.user.save()
        self.assertEqual(self.api.get(self.url).status_code, 200)
        self.assertEqual(self.api.get(history).status_code, 200)
