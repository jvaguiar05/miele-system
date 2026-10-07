from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework import serializers
from rest_framework.test import APIClient

from .serializers import AttachedFileCreateSerializer, AttachedFileUpdateSerializer


class ApprovedRoleAccessTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.guest = user_model.objects.create_user(
            username="release-guest",
            email="release-guest@example.test",
            role="guest",
            approval_status="approved",
        )
        self.employee = user_model.objects.create_user(
            username="release-employee",
            email="release-employee@example.test",
            role="employee",
            approval_status="approved",
        )
        self.api = APIClient()

    def test_guest_is_read_only_on_business_resources(self):
        self.api.force_authenticate(self.guest)
        self.assertEqual(self.api.get("/api/v1/clients/clients/").status_code, 200)
        self.assertEqual(self.api.post("/api/v1/clients/clients/", {}).status_code, 403)
        self.assertEqual(self.api.get("/api/v1/perdcomps/").status_code, 200)
        self.assertEqual(self.api.post("/api/v1/perdcomps/", {}).status_code, 403)
        self.assertEqual(self.api.post("/api/v1/shared/files/", {}).status_code, 403)
        missing_id = "00000000-0000-0000-0000-000000000000"
        self.assertEqual(
            self.api.post(
                f"/api/v1/clients/annotations/by-client/{missing_id}/", {}
            ).status_code,
            403,
        )
        self.assertEqual(
            self.api.post(
                f"/api/v1/perdcomps/annotations/by-perdcomp/{missing_id}/", {}
            ).status_code,
            403,
        )

    def test_employee_reaches_write_validation(self):
        self.api.force_authenticate(self.employee)
        self.assertEqual(self.api.post("/api/v1/clients/clients/", {}).status_code, 400)
        self.assertEqual(self.api.post("/api/v1/perdcomps/", {}).status_code, 400)
        self.assertEqual(self.api.post("/api/v1/shared/files/", {}).status_code, 400)


class AttachedFileLimitTests(TestCase):
    @override_settings(GDRIVE_MAX_FILE_SIZE=4)
    def test_create_and_replace_reject_files_over_configured_limit(self):
        for serializer_class in (
            AttachedFileCreateSerializer,
            AttachedFileUpdateSerializer,
        ):
            with self.subTest(serializer=serializer_class.__name__):
                serializer_instance = serializer_class()
                upload = SimpleUploadedFile("large.pdf", b"12345")
                with self.assertRaises(serializers.ValidationError):
                    serializer_instance.validate_file(upload)

    @override_settings(GDRIVE_MAX_FILE_SIZE=4)
    def test_file_at_configured_limit_is_accepted(self):
        serializer_instance = AttachedFileCreateSerializer()
        upload = SimpleUploadedFile("allowed.pdf", b"1234")
        self.assertEqual(serializer_instance.validate_file(upload).size, 4)
