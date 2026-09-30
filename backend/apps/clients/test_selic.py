from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from .models import SelicAccumulatedRate


class SelicRateTests(TestCase):
    def setUp(self):
        users = get_user_model()
        self.admin = users.objects.create_user(username="selic-admin", email="selic-admin@example.test", role="admin", approval_status="approved")
        self.employee = users.objects.create_user(username="selic-employee", email="selic-employee@example.test", role="employee", approval_status="approved")
        self.api = APIClient()
        self.api.force_authenticate(self.admin)
        self.url = "/api/v1/dashboard/selic/"

    def test_initial_table_matches_provided_period(self):
        response = self.api.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 380)
        self.assertEqual(response.data["years"], list(range(1995, 2027)))
        self.assertFalse(SelicAccumulatedRate.objects.filter(year=1995, month=1).exists())
        self.assertEqual(SelicAccumulatedRate.objects.get(year=1995, month=2).rate, Decimal("440.11"))
        self.assertEqual(SelicAccumulatedRate.objects.get(year=2026, month=9).rate, Decimal("0.00"))
        self.assertFalse(SelicAccumulatedRate.objects.filter(year=2026, month=10).exists())
        self.assertTrue(response.data["can_edit"])

    def test_admin_can_add_edit_and_import(self):
        detail = self.url + "2026/10/"
        created = self.api.patch(detail, {"rate": "1.23", "issued_on": "2026-10-25", "source": "Sicalc"}, format="json")
        self.assertEqual(created.status_code, 200, created.data)
        self.assertEqual(created.data["rate"], "1.23")
        self.assertEqual(created.data["updated_by"], "selic-admin")
        imported = self.api.post(self.url, {"csv": "ano;jan;fev;mar;abr;mai;jun;jul;ago;set;out;nov;dez\n2027;2,50;;;;;;;;;;;", "source": "Sicalc"}, format="json")
        self.assertEqual(imported.status_code, 200, imported.data)
        self.assertEqual(SelicAccumulatedRate.objects.get(year=2027, month=1).rate, Decimal("2.50"))
        self.assertEqual(self.api.delete(detail).status_code, 405)

    def test_employee_reads_but_cannot_write(self):
        self.api.force_authenticate(self.employee)
        result = self.api.get(self.url)
        self.assertEqual(result.status_code, 200)
        self.assertFalse(result.data["can_edit"])
        self.assertEqual(self.api.patch(self.url + "2026/10/", {"rate": "1"}, format="json").status_code, 403)
        self.assertEqual(self.api.post(self.url, {"csv": "x"}, format="json").status_code, 403)
        self.employee.role = "guest"; self.employee.save()
        self.assertEqual(self.api.get(self.url).status_code, 403)
        self.api.force_authenticate(None)
        self.assertEqual(self.api.get(self.url).status_code, 401)

    def test_filter_export_and_validation(self):
        filtered = self.api.get(self.url, {"year": 2026})
        self.assertEqual(filtered.data["count"], 9)
        exported = self.api.get(self.url, {"year": 2026, "export": "csv"})
        self.assertEqual(exported.status_code, 200)
        self.assertEqual(len(exported.content.decode("utf-8-sig").splitlines()), 10)
        self.assertEqual(self.api.get(self.url, {"year": "x"}).status_code, 400)
        self.assertEqual(self.api.patch(self.url + "2026/13/", {"rate": "1"}, format="json").status_code, 400)
        self.assertEqual(self.api.patch(self.url + "2026/10/", {"rate": "-1"}, format="json").status_code, 400)
