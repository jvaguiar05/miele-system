import json
import uuid
from datetime import datetime, timezone as dt_timezone
from unittest.mock import patch
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from rest_framework.test import APIClient
from apps.clients.models import Client
from apps.perdcomps.models import PerDcomp
from .models import AuditLog


class DailyReportTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_user(username="admin-daily", email="admin-daily@example.test", role="admin", approval_status="approved")
        self.employee = get_user_model().objects.create_user(username="employee-daily", email="employee-daily@example.test", role="employee", approval_status="approved")
        self.api = APIClient()
        self.api.force_authenticate(self.admin)
        self.company = Client.objects.create(razao_social="Empresa Teste", cnpj="12345678000100")
        self.process = PerDcomp.objects.create(client_id=self.company.id, created_by_id=self.admin.id, cnpj=self.company.cnpj, numero_perdcomp="PER-TESTE-001", tributo_pedido="COFINS", valor_pedido="100")
        self.ct = ContentType.objects.get_for_model(self.process)
        AuditLog.objects.all().delete()  # Only this test's in-memory database.
        self.url = "/api/v1/activities/daily-report/"
        self.params = {"start": "2026-09-24", "end": "2026-09-24"}

    def log(self, **kwargs):
        values = dict(user=self.admin, content_type=self.ct, object_id=str(self.process.pk), action="UPDATE", correlation_id=uuid.uuid4(), timestamp=datetime(2026, 9, 24, 12, tzinfo=dt_timezone.utc), old_data={"valor_saldo": "100"}, new_data={"valor_saldo": "80"})
        return AuditLog.objects.create(**(values | kwargs))

    def test_timezone_inclusive_start_exclusive_end_and_default_today(self):
        for moment in [datetime(2026, 9, 24, 2, 59, tzinfo=dt_timezone.utc), datetime(2026, 9, 24, 3, tzinfo=dt_timezone.utc), datetime(2026, 9, 25, 2, 59, tzinfo=dt_timezone.utc), datetime(2026, 9, 25, 3, tzinfo=dt_timezone.utc)]:
            self.log(timestamp=moment)
        response = self.api.get(self.url, self.params)
        self.assertEqual(response.data["count"], 2)
        self.assertTrue(response.data["results"][0]["timestamp"].endswith("-03:00"))
        with patch("django.utils.timezone.now", return_value=datetime(2026, 9, 24, 12, tzinfo=dt_timezone.utc)):
            self.assertEqual(self.api.get(self.url).data["count"], 2)

    def test_permissions_and_export_cannot_expand_employee_scope(self):
        self.log(new_data={"valor_saldo": "ADMIN-ONLY"})
        self.log(user=self.employee, new_data={"valor_saldo": "EMPLOYEE-OWN"})
        self.log(user=None, new_data={"valor_saldo": "SYSTEM-ONLY"})
        self.api.force_authenticate(self.employee)
        result = self.api.get(self.url, self.params)
        self.assertEqual(result.data["count"], 1)
        self.assertEqual(result.data["scope"], "own")
        self.assertEqual(self.api.get(self.url, {**self.params, "user": "admin-daily"}).data["count"], 0)
        exported = self.api.get(self.url, {**self.params, "export": "csv"}).content.decode("utf-8-sig")
        self.assertIn("EMPLOYEE-OWN", exported)
        self.assertNotIn("ADMIN-ONLY", exported)
        self.assertNotIn("SYSTEM-ONLY", exported)
        self.api.force_authenticate(None)
        self.assertEqual(self.api.get(self.url).status_code, 401)
        self.employee.role = "guest"
        self.employee.save()
        self.api.force_authenticate(self.employee)
        self.assertEqual(self.api.get(self.url).status_code, 403)

    def test_sensitive_data_nested_values_and_noop_fields(self):
        self.log(old_data={"status": "TRANSMITIDO", "valor_saldo": "100", "password": "SENSITIVE-A"}, new_data={"status": "TRANSMITIDO", "valor_saldo": "80", "password": "SENSITIVE-B", "token": "SENSITIVE-C", "payload": {"secret": "SENSITIVE-D"}, "numero": {"secret": "SENSITIVE-E"}}, metadata={"headers": {"Authorization": "SENSITIVE-F"}, "type": "due_date_override", "reason": "Ajuste de teste"})
        response = self.api.get(self.url, self.params)
        output = json.dumps(response.data)
        for letter in "ABCDEF":
            self.assertNotIn("SENSITIVE-" + letter, output)
        fields = [c["field"] for c in response.data["results"][0]["changes"]]
        self.assertNotIn("Status", fields)
        self.assertIn("Saldo", fields)
        self.assertEqual(response.data["results"][0]["reason"], "Ajuste de teste")
        export = self.api.get(self.url, {**self.params, "export": "csv"}).content.decode("utf-8-sig")
        self.assertNotIn("SENSITIVE-", export)

    def test_filters_pagination_csv_all_pages_and_formula_escape(self):
        for _ in range(21):
            self.log(new_data={"valor_saldo": "=1+1"})
        response = self.api.get(self.url, {**self.params, "client": "Empresa", "perdcomp": "PER-TESTE", "action": "UPDATE", "origin": "user"})
        self.assertEqual(response.data["count"], 21)
        self.assertEqual(len(response.data["results"]), 20)
        self.assertEqual(len(self.api.get(self.url, {**self.params, "page": 2}).data["results"]), 1)
        export = self.api.get(self.url, {**self.params, "page": 2, "export": "csv"}).content.decode("utf-8-sig")
        self.assertEqual(len(export.splitlines()), 22)
        self.assertIn("'=1+1", export)
        self.assertEqual(self.api.get(self.url, {**self.params, "client": "ausente"}).data["count"], 0)

    def test_invalid_dates_readonly_and_deleted_record_history(self):
        self.log(new_data={"numero_perdcomp": "REMOVIDO", "client_id": self.company.id})
        self.process.delete()
        result = self.api.get(self.url, {**self.params, "perdcomp": "REMOVIDO"})
        self.assertEqual(result.data["count"], 1)
        self.assertIsNone(result.data["results"][0]["href"])
        self.assertEqual(self.api.get(self.url, {"start": "2026-09-25", "end": "2026-09-24"}).status_code, 400)
        self.assertEqual(self.api.post(self.url, {}).status_code, 405)

    def test_system_event_not_misattributed(self):
        self.log(user=None, action="CUSTOM", old_data={}, new_data={}, metadata={"type": "system"})
        response = self.api.get(self.url, {**self.params, "origin": "system"})
        self.assertEqual(response.data["count"], 1)
        self.assertIn("autoria não registrada", response.data["results"][0]["origin"])
