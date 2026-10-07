from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient


class AuditEndpointPermissionTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.admin = user_model.objects.create_user(
            username="audit-admin",
            email="audit-admin@example.test",
            role="admin",
            approval_status="approved",
        )
        self.employee = user_model.objects.create_user(
            username="audit-employee",
            email="audit-employee@example.test",
            role="employee",
            approval_status="approved",
        )
        self.api = APIClient()

    def test_global_audit_endpoints_are_admin_only(self):
        self.api.force_authenticate(self.employee)
        self.assertEqual(self.api.get("/api/v1/activities/logs/").status_code, 403)
        self.assertEqual(
            self.api.get(
                "/api/v1/activities/recent-logs/",
                {"since": timezone.now().isoformat()},
            ).status_code,
            403,
        )

        self.api.force_authenticate(self.admin)
        self.assertEqual(self.api.get("/api/v1/activities/logs/").status_code, 200)
        self.assertEqual(
            self.api.get(
                "/api/v1/activities/recent-logs/",
                {"since": timezone.now().isoformat()},
            ).status_code,
            200,
        )

    def test_employee_can_still_read_own_audit_log_endpoint(self):
        self.api.force_authenticate(self.employee)
        self.assertEqual(
            self.api.get("/api/v1/activities/my-logs/").status_code,
            200,
        )
