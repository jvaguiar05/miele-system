from datetime import date
from unittest.mock import patch
from django.test import TestCase, SimpleTestCase, override_settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from apps.clients.models import Client
from common.audit.models import AuditLog
from .models import PerDcomp
from .deadlines import automatic_due_date, alert_start


class DeadlineCalendarTests(SimpleTestCase):
    def test_anniversary_weekend_holiday_and_leap_year(self):
        self.assertEqual(automatic_due_date(date(2025, 9, 24)), date(2026, 9, 24))
        self.assertEqual(automatic_due_date(date(2025, 10, 10)), date(2026, 10, 13))
        self.assertEqual(automatic_due_date(date(2024, 2, 29)), date(2025, 2, 28))
        self.assertEqual(alert_start(date(2026, 11, 9)), date(2026, 9, 24))

    @override_settings(DASHBOARD_EXTRA_HOLIDAYS=["2026-09-24"])
    def test_additional_calendar_date(self):
        self.assertEqual(automatic_due_date(date(2025, 9, 24)), date(2026, 9, 25))


class DeadlineApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="deadlines", role="admin", approval_status="approved", is_staff=True)
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.company = Client.objects.create(razao_social="Teste prazo", cnpj="12345678000100", is_active=True)
        self.payload = {"client_cnpj": self.company.cnpj, "numero_perdcomp": "TESTE", "data_transmissao": "2025-10-10", "tributo_pedido": "COFINS", "valor_pedido": "100", "valor_saldo": "50", "status": "TRANSMITIDO"}

    def test_create_preview_edit_and_audit(self):
        preview = self.client.get("/api/v1/perdcomps/deadline-preview/", {"transmission": "2025-10-10"})
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.data["due"], "2026-10-13")
        created = self.client.post("/api/v1/perdcomps/", self.payload, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data["data_vencimento"], "2026-10-13")
        url = f'/api/v1/perdcomps/{created.data["id"]}/'
        unchanged = self.client.patch(url, {"valor_saldo": "45"}, format="json")
        self.assertEqual(unchanged.status_code, 200, unchanged.data)
        self.assertEqual(unchanged.data["data_vencimento"], "2026-10-13")
        rejected = self.client.patch(url, {"data_vencimento": "2026-11-09"}, format="json")
        self.assertEqual(rejected.status_code, 400)
        accepted = self.client.patch(url, {"data_vencimento": "2026-11-09", "due_date_reason": "Prazo revisado para teste"}, format="json")
        self.assertEqual(accepted.status_code, 200, accepted.data)
        self.assertTrue(AuditLog.objects.filter(metadata__type="due_date_override", user=self.user).exists())
        recalculated = self.client.patch(url, {"recalculate_due_date": True}, format="json")
        self.assertEqual(recalculated.data["data_vencimento"], "2026-10-13")

    def test_report_filters_csv_and_permissions(self):
        for due, number in [(date(2026, 11, 9), "=TESTE"), (date(2026, 11, 10), "FORA"), (date(2026, 9, 23), "VENCIDO")]:
            PerDcomp.objects.create(client_id=self.company.id, created_by_id=self.user.id, cnpj=self.company.cnpj, numero_perdcomp=number, data_transmissao=date(2025, 9, 1), data_vencimento=due, tributo_pedido="COFINS", valor_pedido="100", status="TRANSMITIDO")
        url = "/api/v1/perdcomps/upcoming-report/"
        with patch("apps.clients.dashboard_operations.timezone.localdate", return_value=date(2026, 9, 24)):
            report = self.client.get(url)
            self.assertEqual(report.status_code, 200, report.data)
            self.assertEqual(report.data["count"], 1)
            self.assertEqual(self.client.get(url, {"include_overdue": "true"}).data["count"], 2)
            self.assertEqual(self.client.get(url, {"client": "inexistente"}).data["count"], 0)
            self.assertEqual(self.client.get(url, {"status": "EM_PROCESSAMENTO"}).data["count"], 0)
            self.assertEqual(self.client.get(url, {"start": "2026-11-10", "end": "2026-11-01"}).status_code, 400)
            csv = self.client.get(url, {"export": "csv"})
            self.assertContains(csv, "'=TESTE")
            self.assertNotContains(csv, "FORA")
        self.client.force_authenticate(None)
        self.assertIn(self.client.get(url).status_code, (401, 403))
