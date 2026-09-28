from datetime import date
from unittest.mock import patch
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from apps.perdcomps.models import PerDcomp
from .models import Client, QuarterSnapshot


class QuarterTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="quarter-test", role="admin", approval_status="approved")
        self.api = APIClient()
        self.api.force_authenticate(self.user)
        self.company = Client.objects.create(razao_social="Empresa fictícia", cnpj="12345678000100", is_active=True)
        self.process = PerDcomp.objects.create(client_id=self.company.id, created_by_id=self.user.id, cnpj=self.company.cnpj, numero_perdcomp="TESTE", tributo_pedido="COFINS", valor_pedido="100.50", valor_saldo="60.25", status="TRANSMITIDO")
        self.url = "/api/v1/dashboard/quarters/snapshots/"

    def capture(self, kind="position", today=date(2026, 9, 24)):
        with patch("django.utils.timezone.localdate", return_value=today):
            return self.api.post(self.url, {"year": today.year, "quarter": (today.month - 1) // 3 + 1, "kind": kind, "note": "Revisado"}, format="json")

    def test_snapshot_preserves_values_names_and_export(self):
        response = self.capture()
        self.assertEqual(response.status_code, 201, response.data)
        url = self.url + response.data["id"] + "/"
        self.process.valor_saldo = "1.00"
        self.process.save()
        self.company.razao_social = "Nome alterado"
        self.company.save()
        saved = self.api.get(url).data
        self.assertEqual(saved["payload"]["balance"], "60.25")
        self.assertEqual(saved["payload"]["companies"][0]["name"], "Empresa fictícia")
        self.assertEqual(saved["captured_by"], "quarter-test")
        self.assertContains(self.api.get(url, {"export": "csv"}), "60.25")
        self.assertEqual(self.api.patch(url, {"balance": "999"}).status_code, 405)
        self.assertEqual(self.api.delete(url).status_code, 405)

    def test_closing_date_and_unique_closing(self):
        self.assertEqual(self.capture("closing").status_code, 400)
        self.assertEqual(self.capture("closing", date(2026, 9, 30)).status_code, 201)
        self.assertEqual(self.capture("closing", date(2026, 9, 30)).status_code, 409)
        self.assertEqual(QuarterSnapshot.objects.filter(kind="closing").count(), 1)

    def test_missing_balance_blocks_closing_but_allows_position(self):
        self.process.valor_saldo = ""
        self.process.save()
        self.assertEqual(self.capture("closing", date(2026, 9, 30)).status_code, 400)
        saved = self.capture()
        self.assertEqual(saved.status_code, 201)
        self.assertEqual(saved.data["missing"], 1)

    def test_period_scope_permissions_and_previous_comparison(self):
        self.capture("closing", date(2026, 9, 30))
        self.process.valor_saldo = "70.25"
        self.process.save()
        with patch("django.utils.timezone.localdate", return_value=date(2026, 10, 1)):
            position = self.api.get("/api/v1/dashboard/quarters/current/").data
            self.assertEqual(position["difference"], "10.00")
            self.assertFalse(position["can_close"])
            self.assertEqual(self.api.post(self.url, {"year": 2026, "quarter": 3, "kind": "position"}, format="json").status_code, 400)
        self.user.role = "employee"
        self.user.save()
        self.assertEqual(self.api.get(self.url).status_code, 200)
        self.assertEqual(self.capture().status_code, 403)
        self.api.force_authenticate(None)
        self.assertEqual(self.api.get(self.url).status_code, 401)
