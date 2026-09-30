from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import SelicAccumulatedRate, SelicAccumulatedReport


class SelicReportTests(TestCase):
    def setUp(self):
        users = get_user_model()
        self.admin = users.objects.create_user(username="selic-admin", email="admin@example.test", role="admin", approval_status="approved")
        self.employee = users.objects.create_user(username="selic-user", email="user@example.test", role="employee", approval_status="approved")
        self.api = APIClient(); self.api.force_authenticate(self.admin)
        self.url = "/api/v1/dashboard/selic/"

    def test_initial_report_preserves_blank_and_zero(self):
        response = self.api.get(self.url)
        self.assertEqual(response.status_code, 200)
        report = response.data["active"]
        self.assertEqual((report["reference_year"], report["reference_month"], report["value_count"]), (2026, 9, 380))
        self.assertNotIn("1995-01", report["values"])
        self.assertEqual(report["values"]["1995-02"], "440.11")
        self.assertEqual(report["values"]["2026-09"], "0.00")
        self.assertNotIn("2026-10", report["values"])

    def test_manual_correction_creates_audited_version(self):
        original = SelicAccumulatedReport.objects.get(is_active=True)
        url = f"{self.url}{original.public_id}/2026/9/"
        response = self.api.patch(url, {"rate": "0.01", "reason": "Correção conforme documento oficial"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        original.refresh_from_db(); self.assertFalse(original.is_active)
        corrected = SelicAccumulatedReport.objects.get(is_active=True)
        self.assertEqual(corrected.version, 2)
        rate = SelicAccumulatedRate.objects.get(report=corrected, year=2026, month=9)
        self.assertEqual(rate.rate, Decimal("0.01")); self.assertEqual(rate.corrected_by, self.admin)
        self.assertIn("documento oficial", rate.correction_reason)

    @patch("apps.clients.selic_views.parse_accumulated_pdf")
    def test_preview_only_saves_after_confirmation_and_keeps_pdf(self, parser):
        parser.return_value = {"report_type": "selic_accumulated_payment", "reference_year": 2026, "reference_month": 10,
            "issued_on": "2026-10-25", "source": "Sicalc", "page_count": 4, "value_count": 1, "blank_count": 3,
            "values": {"2026-10": "0.00"}, "sha256": "a" * 64}
        before = SelicAccumulatedReport.objects.count()
        response = self.api.post(self.url + "import/preview/", {"file": self._pdf()}, format="multipart")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(SelicAccumulatedReport.objects.count(), before)
        self.assertTrue(response.data["token"]); self.assertEqual(response.data["preview"]["next_version"], 1)
        confirmed = self.api.post(self.url + "import/confirm/", {"token": response.data["token"]}, format="json")
        self.assertEqual(confirmed.status_code, 201, confirmed.data)
        stored = SelicAccumulatedReport.objects.get(reference_year=2026, reference_month=10)
        self.assertEqual(bytes(stored.original_content), b"%PDF-test")
        self.assertEqual(SelicAccumulatedReport.objects.count(), before + 1)

    def _pdf(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        return SimpleUploadedFile("selic.pdf", b"%PDF-test", content_type="application/pdf")

    def test_employee_can_read_but_cannot_change(self):
        report = SelicAccumulatedReport.objects.get(is_active=True)
        self.api.force_authenticate(self.employee)
        self.assertEqual(self.api.get(self.url).status_code, 200)
        self.assertFalse(self.api.get(self.url).data["can_edit"])
        self.assertEqual(self.api.post(self.url + "import/preview/", {"file": self._pdf()}, format="multipart").status_code, 403)
        self.assertEqual(self.api.patch(f"{self.url}{report.public_id}/2026/9/", {"rate": "1", "reason": "Sem permissão"}).status_code, 403)

    @patch("apps.clients.selic_views.drive_service.upload_stream", side_effect=Exception("drive unavailable"))
    @patch("apps.clients.selic_views.settings.GDRIVE_CLIENT_ID", "client")
    @patch("apps.clients.selic_views.settings.GDRIVE_CLIENT_SECRET", "secret")
    @patch("apps.clients.selic_views.settings.GDRIVE_REFRESH_TOKEN", "token")
    @patch("apps.clients.selic_views.parse_accumulated_pdf")
    def test_drive_failure_returns_clear_error_without_saving(self, parser, _upload):
        parser.return_value = {"report_type": "selic_accumulated_payment", "reference_year": 2026, "reference_month": 10,
            "issued_on": "2026-10-25", "source": "Sicalc", "page_count": 4, "value_count": 1, "blank_count": 3,
            "values": {"2026-10": "0.00"}, "sha256": "b" * 64}
        preview = self.api.post(self.url + "import/preview/", {"file": self._pdf()}, format="multipart")
        confirmed = self.api.post(self.url + "import/confirm/", {"token": preview.data["token"]}, format="json")
        self.assertEqual(confirmed.status_code, 502)
        self.assertIn("Google Drive", confirmed.data["detail"])
        self.assertFalse(SelicAccumulatedReport.objects.filter(reference_month=10).exists())
