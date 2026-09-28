from datetime import date
from decimal import Decimal
from unittest.mock import patch
from django.test import TestCase, SimpleTestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory, force_authenticate
from .models import Client
from apps.perdcomps.models import PerDcomp
from .dashboard_operations import alert_start, money, operations


class CalendarTests(SimpleTestCase):
    def test_exact_window_and_next_day(self):
        self.assertEqual(alert_start(date(2026, 11, 9)), date(2026, 9, 24))
        self.assertEqual(alert_start(date(2026, 11, 10)), date(2026, 9, 25))

    def test_decimal_formats_and_invalid_values(self):
        self.assertEqual(money("R$ 1.234,56"), Decimal("1234.56"))
        self.assertEqual(money("1234.56"), Decimal("1234.56"))
        self.assertIsNone(money("NaN"))
        self.assertIsNone(money(""))


class DashboardTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="dashboard-test", role="admin", approval_status="approved")
        self.client_record = Client.objects.create(razao_social="Empresa ficticia", cnpj="00000000000000", is_active=True)

    def create_record(self, **changes):
        values = dict(client_id=self.client_record.id, created_by_id=self.user.id, cnpj="00000000000000", numero_perdcomp="TESTE", tributo_pedido="COFINS", data_transmissao=date(2025, 11, 9), data_vencimento=date(2026, 11, 9), status="TRANSMITIDO", valor_pedido="100.10", valor_saldo="40.05")
        return PerDcomp.objects.create(**(values | changes))

    def response(self, authenticated=True):
        request = APIRequestFactory().get("/api/v1/dashboard/operations/")
        if authenticated:
            force_authenticate(request, self.user)
        with patch("apps.clients.dashboard_operations.timezone.localdate", return_value=date(2026, 9, 24)):
            return operations(request)

    def test_auth_required(self):
        self.assertIn(self.response(False).status_code, (401, 403))

    def test_scope_totals_alert_boundaries_and_closed_status(self):
        self.create_record()
        self.create_record(data_vencimento=date(2026, 11, 10))
        self.create_record(status="RASCUNHO")
        self.create_record(status="CANCELADO")
        self.create_record(status="DEFERIDO", valor_saldo="0")
        self.create_record(is_active=False)
        self.create_record(data_vencimento=date(2026, 9, 23), status="VENCIDO")
        self.create_record(data_vencimento=date(2026, 9, 24))
        response = self.response()
        self.assertEqual(response.status_code, 200)
        data = response.data
        self.assertEqual(data["transmitted_amount"], "500.50")
        self.assertEqual(data["balance"], "160.20")
        self.assertEqual([a["severity"] for a in data["alerts"]], ["overdue", "today", "upcoming"])
        self.assertTrue(data["quarter_alert"])
        self.assertEqual(sum(s["count"] for s in data["statuses"]), data["processes"])

    def test_empty_and_missing_balances(self):
        self.assertEqual(self.response().data["alerts"], [])
        self.create_record(valor_saldo="")
        self.assertEqual(self.response().data["missing_values"], 1)
