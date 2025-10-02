from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django_otp.models import Device
from common.audit.signals import AuditableMixin
import uuid


# Define your models here
class User(AbstractUser, AuditableMixin):
    # Flag para auditoria automática
    __audit__ = True

    class ApprovalStatus(models.TextChoices):
        PENDING = "pending", _("Pending")
        APPROVED = "approved", _("Approved")
        DECLINED = "declined", _("Declined")

    class UserRole(models.TextChoices):
        EMPLOYEE = "employee", _("Employee")
        GUEST = "guest", _("Guest")
        ADMIN = "admin", _("Admin")

    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    approval_status = models.CharField(
        max_length=10,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.PENDING,
    )

    role = models.CharField(
        max_length=20,
        choices=UserRole.choices,
        default=UserRole.EMPLOYEE,
        help_text=_("User role that determines permissions"),
    )

    deleted_at = models.DateTimeField(null=True, blank=True)
    suspended_at = models.DateTimeField(null=True, blank=True)
    email = models.EmailField(unique=True, blank=False, null=False)

    def soft_delete(self):
        self.deleted_at = timezone.now()
        self.save()

    def restore(self):
        self.deleted_at = None
        self.save()

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")


class TOTPDevice(Device):
    key = models.CharField(max_length=80, unique=True)
    step = models.PositiveSmallIntegerField(default=30)
    t0 = models.BigIntegerField(default=0)
    digits = models.PositiveSmallIntegerField(default=6)
    tolerance = models.PositiveSmallIntegerField(default=1)
    drift = models.IntegerField(default=0)
    user = models.ForeignKey(
        "User", on_delete=models.CASCADE, related_name="totp_devices"
    )


class SensibleDataChangeRequest(models.Model):
    # Flag para auditoria automática - desabilitado pois este modelo serve como seu próprio audit trail
    __audit__ = False

    class RequestType(models.TextChoices):
        EMAIL_CHANGE = "email_change", _("Email Change")
        ROLE_CHANGE = "role_change", _("Role Change")
        SENSITIVE_PROFILE_CHANGE = "sensitive_profile_change", _(
            "Sensitive Profile Change"
        )

    class RequestStatus(models.TextChoices):
        PENDING = "pending", _("Pending")
        APPROVED = "approved", _("Approved")
        REJECTED = "rejected", _("Rejected")

    # Chave primária interna (int) para performance em FK
    id = models.BigAutoField(primary_key=True)
    # ID público (UUID) para exposição segura
    public_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="change_requests"
    )
    request_type = models.CharField(max_length=30, choices=RequestType.choices)
    status = models.CharField(
        max_length=10, choices=RequestStatus.choices, default=RequestStatus.PENDING
    )

    # JSON field to store the requested changes
    requested_changes = models.JSONField(
        help_text=_("JSON containing the requested changes")
    )
    justification = models.TextField(help_text=_("Reason for the change request"))

    # Admin fields
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_requests",
        limit_choices_to={"role": User.UserRole.ADMIN},
    )
    review_notes = models.TextField(
        blank=True, help_text=_("Admin notes about the review")
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Sensible Data Change Request")
        verbose_name_plural = _("Sensible Data Change Requests")
        indexes = [
            models.Index(fields=["public_id"]),
            models.Index(fields=["user"]),
            models.Index(fields=["status"]),
            models.Index(fields=["created_at"]),
        ]
