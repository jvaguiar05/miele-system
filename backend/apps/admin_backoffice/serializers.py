from rest_framework import serializers
from django.contrib.auth import get_user_model
from common.approvals.models import ApprovalRequest

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    """Serializer básico para usuários."""

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "email"]
        read_only_fields = ["id"]


class ApprovalRequestSerializer(serializers.ModelSerializer):
    """Serializer para solicitações de aprovação no painel admin."""

    requested_by = UserSerializer(read_only=True)
    approved_by = UserSerializer(read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    action_display = serializers.CharField(source="get_action_display", read_only=True)

    class Meta:
        model = ApprovalRequest
        fields = [
            "id",
            "subject",
            "action",
            "action_display",
            "status",
            "status_display",
            "resource_type",
            "resource_id",
            "payload_diff",
            "reason",
            "requested_by",
            "approved_by",
            "created_at",
            "updated_at",
            "approved_at",
            "executed_at",
            "metadata",
            "approval_notes",
        ]
        read_only_fields = [
            "id",
            "requested_by",
            "approved_by",
            "created_at",
            "updated_at",
            "approved_at",
            "executed_at",
            "status_display",
            "action_display",
        ]


class ApprovalActionSerializer(serializers.Serializer):
    """Serializer para ações de aprovação/rejeição."""

    approval_action = serializers.ChoiceField(choices=["approve", "reject"])
    notes = serializers.CharField(required=False, allow_blank=True)

    def validate_approval_action(self, value):
        approval_request = self.context.get("approval_request")
        if approval_request and not approval_request.is_pending:
            raise serializers.ValidationError(
                "Apenas solicitações pendentes podem ser aprovadas ou rejeitadas."
            )
        return value
