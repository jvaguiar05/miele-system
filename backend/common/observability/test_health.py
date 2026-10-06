from unittest.mock import patch

from django.db import connections
from django.db.utils import DatabaseError
from django.test import RequestFactory, TestCase

from .health import live, ready


class HealthCheckTests(TestCase):
    def setUp(self):
        self.request = RequestFactory().get("/health/ready")

    def test_live_does_not_depend_on_database(self):
        response = live(self.request)

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {"status": "live"})

    def test_ready_checks_database(self):
        response = ready(self.request)

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {"status": "ready"})

    def test_ready_returns_503_when_database_is_unavailable(self):
        with patch.object(
            connections["default"], "cursor", side_effect=DatabaseError("offline")
        ):
            response = ready(self.request)

        self.assertEqual(response.status_code, 503)
        self.assertJSONEqual(response.content, {"status": "unavailable"})
