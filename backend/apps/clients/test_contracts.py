from datetime import date
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from apps.perdcomps.models import PerDcomp
from .models import Client, ClientContract


class ClientContractTests(TestCase):
    def setUp(self):
        users = get_user_model()
        self.admin = users.objects.create_user(username="contract-admin", email="contract-admin@example.test", role="admin", approval_status="approved")
        self.employee = users.objects.create_user(username="contract-employee", email="contract-employee@example.test", role="employee", approval_status="approved")
        self.client = Client.objects.create(razao_social="Empresa Contrato", cnpj="11222333000144")
        self.api = APIClient()
        self.api.force_authenticate(self.admin)
        self.url = f"/api/v1/clients/{self.client.public_id}/contracts/"

    def process(self, transmitted, requested, compensated="", received=""):
        return PerDcomp.objects.create(client_id=self.client.id, created_by_id=self.admin.id, cnpj=self.client.cnpj, numero_perdcomp=f"P-{transmitted}", tributo_pedido="COFINS", data_transmissao=transmitted, valor_pedido=requested, valor_compensado=compensated, valor_recebido=received)

    def test_different_periods_and_all_three_bases(self):
        self.process(date(2026, 1, 15), "R$ 1.000,00", "400,00", "100.00")
        self.process(date(2026, 7, 15), "2000.00", "1.000,00", "500")
        first = self.api.post(self.url, {"percentage": "10", "starts_on": "2026-01-01", "ends_on": "2026-06-30", "reference": "A"}, format="json")
        second = self.api.post(self.url, {"percentage": "20", "starts_on": "2026-07-01", "billing_evolution_requested": True}, format="json")
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(second.status_code, 201, second.data)
        result = self.api.get(self.url).data
        self.assertEqual(result["mode"], "informational")
        self.assertEqual(result["uncovered_processes"], 0)
        newest = result["contracts"][0]
        self.assertEqual(newest["totals"]["requested"], {"base": "2000.00", "calculated": "400.00"})
        self.assertEqual(newest["totals"]["compensated"], {"base": "1000.00", "calculated": "200.00"})
        self.assertEqual(newest["totals"]["received"], {"base": "500.00", "calculated": "100.00"})
        self.assertEqual(newest["totals"]["contractual"], {"base": "1500.00", "calculated": "300.00", "formula": "valor_compensado + valor_recebido"})
        self.assertEqual(newest["calculation_basis"], "compensated_plus_received")
        self.assertTrue(newest["billing_evolution_requested"])

    def test_contractual_base_treats_empty_values_as_zero(self):
        self.process(date(2026, 1, 15), "999", "", "250,50")
        created = self.api.post(self.url, {"percentage": "10", "starts_on": "2026-01-01"}, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        result = self.api.get(self.url).data["contracts"][0]
        self.assertEqual(result["totals"]["contractual"]["base"], "250.50")
        self.assertEqual(result["totals"]["contractual"]["calculated"], "25.05")

    def test_overlap_invalid_dates_and_uncovered(self):
        self.process(date(2025, 12, 31), "100")
        self.assertEqual(self.api.post(self.url, {"percentage": "10", "starts_on": "2026-01-01", "ends_on": "2026-12-31"}, format="json").status_code, 201)
        self.assertEqual(self.api.post(self.url, {"percentage": "12", "starts_on": "2026-06-01"}, format="json").status_code, 400)
        self.assertEqual(self.api.post(self.url, {"percentage": "12", "starts_on": "2027-02-01", "ends_on": "2027-01-01"}, format="json").status_code, 400)
        self.assertEqual(self.api.get(self.url).data["uncovered_processes"], 1)

    def test_permissions_update_and_no_delete(self):
        created = self.api.post(self.url, {"percentage": "5", "starts_on": "2026-01-01"}, format="json")
        detail = self.url + created.data["id"] + "/"
        self.assertEqual(self.api.patch(detail, {"billing_evolution_requested": True}, format="json").status_code, 200)
        self.assertTrue(ClientContract.objects.get().billing_evolution_requested)
        self.assertEqual(self.api.delete(detail).status_code, 405)
        self.api.force_authenticate(self.employee)
        self.assertEqual(self.api.get(self.url).status_code, 200)
        self.assertEqual(self.api.post(self.url, {"percentage": "9", "starts_on": "2027-01-01"}, format="json").status_code, 403)
        self.assertEqual(self.api.patch(detail, {"percentage": "9"}, format="json").status_code, 403)
        self.api.force_authenticate(None)
        self.assertEqual(self.api.get(self.url).status_code, 401)
