from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory
from apps.clients.models import Client
from .models import PerDcomp
from .serializers import PerDcompSerializer, PerDcompSensitiveSerializer


class DraftStatusRetirementTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="status-test", email="status-test@example.test")
        self.client = Client.objects.create(razao_social="Cliente Status", cnpj="22333444000155")
        self.request = APIRequestFactory().post("/")
        self.request.user = self.user

    def data(self, status=None):
        result = {"client_cnpj": self.client.cnpj, "numero_perdcomp": "STATUS-1", "tributo_pedido": "COFINS", "valor_pedido": "100"}
        if status is not None:
            result["status"] = status
        return result

    def test_new_defaults_to_transmitted_and_rejects_draft(self):
        serializer = PerDcompSerializer(data=self.data(), context={"request": self.request})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["status"], "TRANSMITIDO")
        draft = PerDcompSerializer(data=self.data("RASCUNHO"), context={"request": self.request})
        self.assertFalse(draft.is_valid())
        self.assertIn("status", draft.errors)
        sensitive = PerDcompSensitiveSerializer(instance=PerDcomp(status="TRANSMITIDO"), data={"status": "RASCUNHO"}, partial=True)
        self.assertFalse(sensitive.is_valid())

    def test_existing_draft_is_preserved_and_can_leave_draft(self):
        record = PerDcomp.objects.create(client_id=self.client.id, created_by_id=self.user.id, cnpj=self.client.cnpj, numero_perdcomp="LEGADO", tributo_pedido="COFINS", valor_pedido="100", status="RASCUNHO")
        unchanged = PerDcompSerializer(record, data={"status": "RASCUNHO"}, partial=True, context={"request": self.request})
        self.assertTrue(unchanged.is_valid(), unchanged.errors)
        leaving = PerDcompSerializer(record, data={"status": "TRANSMITIDO"}, partial=True, context={"request": self.request})
        self.assertTrue(leaving.is_valid(), leaving.errors)
