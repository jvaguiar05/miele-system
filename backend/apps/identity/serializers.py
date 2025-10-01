from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import authenticate
from django.contrib.auth import get_user_model
from .models import User, SensibleDataChangeRequest
from .exceptions import (
    InvalidCredentialsError,
    AccountInactiveError,
    AccountPendingError,
    AccountDeclinedError,
    MissingCredentialsError,
    PasswordMismatchError,
    EmailAlreadyExistsError,
)
from common.approvals.services import ApprovalService

User = get_user_model()


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Custom token serializer that provides better error handling for login attempts.
    """

    default_error_messages = {"no_active_account": "Invalid username or password."}

    def validate(self, attrs):
        """
        Override validate to provide custom error handling for all login scenarios.
        """
        username = attrs.get("username")
        password = attrs.get("password")

        if not username or not password:
            raise MissingCredentialsError()

        # First, check if user exists and get their status
        try:
            user = User.objects.get(username=username)

            # Check if user is active
            if not user.is_active:
                raise AccountInactiveError()

            # Check approval status BEFORE attempting authentication
            if user.approval_status == User.ApprovalStatus.PENDING:
                raise AccountPendingError()
            elif user.approval_status == User.ApprovalStatus.DECLINED:
                raise AccountDeclinedError()

        except User.DoesNotExist:
            # User doesn't exist - let authentication fail naturally
            # This will result in "Invalid username or password" message
            pass

        # Now attempt authentication
        try:
            data = super().validate(attrs)

            # Log successful login to audit (JWT doesn't trigger user_logged_in signal)
            user = self.user  # User is set by parent validate method
            if user:
                from common.audit.services import AuditService

                # Get request object to extract IP
                request = self.context.get("request")
                metadata = {}
                if request:
                    ip_address = request.META.get("REMOTE_ADDR")
                    if ip_address:
                        metadata["ip"] = ip_address
                metadata["login_type"] = "api"

                # Log login action using the user as content object
                AuditService.log_action(
                    action="LOGIN", content_object=user, user=user, metadata=metadata
                )

            return data
        except serializers.ValidationError as e:
            # Check if it's an authentication error (wrong password)
            if (
                "no_active_account" in str(e.detail)
                or "authentication" in str(e.detail).lower()
            ):
                raise InvalidCredentialsError()
            # Re-raise other validation errors
            raise e


# Define your serializers here
class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class RBACSerializer(serializers.Serializer):
    groups = serializers.ListField(child=serializers.CharField())


class TOTPEnrollSerializer(serializers.Serializer):
    key = serializers.CharField()


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["username", "first_name", "last_name"]


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField()
    new_password = serializers.CharField()


class AuthThrottleSerializer(serializers.Serializer):
    message = serializers.CharField()


class UserRegistrationSerializer(serializers.Serializer):
    username = serializers.CharField()
    email = serializers.EmailField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, data):
        if data["password"] != data["confirm_password"]:
            raise PasswordMismatchError()
        return data

    def create(self, validated_data):
        validated_data.pop(
            "confirm_password"
        )  # Remove confirm_password as it's not needed for user creation
        user = User.objects.create_user(
            username=validated_data["username"],
            email=validated_data["email"],
            first_name=validated_data["first_name"],
            last_name=validated_data["last_name"],
            password=validated_data["password"],
            approval_status=User.ApprovalStatus.PENDING,
            role=User.UserRole.EMPLOYEE,  # Default role for new registrations
        )

        # Create approval request for user account activation
        ApprovalService.create_request(
            subject=f"Ativação de conta para {user.username}",
            action="activate",
            resource_type="identity.User",
            resource_id=str(user.id),  # Use the actual primary key (id), not public_id
            payload_diff={
                "old_data": {"approval_status": "pending", "is_active": False},
                "new_data": {"approval_status": "approved", "is_active": True},
            },
            reason=f"Solicitação de ativação de conta para novo usuário: {user.username} ({user.email})",
            requested_by=user,
            metadata={
                "user_details": {
                    "username": user.username,
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "role": user.role,
                    "registration_date": user.date_joined.isoformat(),
                    "public_id": str(
                        user.public_id
                    ),  # Store public_id in metadata for reference
                }
            },
        )

        return user


class UserDeleteSerializer(serializers.Serializer):
    password = serializers.CharField(required=True)


class SensibleDataChangeRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = SensibleDataChangeRequest
        fields = [
            "id",
            "request_type",
            "status",
            "requested_changes",
            "justification",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "status", "created_at", "updated_at"]


class EmailChangeRequestSerializer(serializers.Serializer):
    new_email = serializers.EmailField(required=True)
    justification = serializers.CharField(max_length=500, required=True)

    def validate_new_email(self, value):
        if User.objects.filter(email=value).exists():
            raise EmailAlreadyExistsError()
        return value


class ReviewChangeRequestSerializer(serializers.Serializer):
    review_action = serializers.ChoiceField(
        choices=[("approve", "Approve Request"), ("reject", "Reject Request")],
        required=True,
        help_text="Ação de revisão: aprovar ou rejeitar a solicitação",
    )
    review_notes = serializers.CharField(
        max_length=1000, required=False, allow_blank=True
    )
