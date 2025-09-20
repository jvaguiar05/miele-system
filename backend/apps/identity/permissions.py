from rest_framework import permissions
from .models import User


class IsEmployee(permissions.BasePermission):
    """
    Permission for Employee role:
    - Can view all client and perdcomp information (except sensible data)
    - Can change clients and perdcomps
    - Can view logs about own actions only
    - Can change own profile
    - Needs approval for sensible information changes
    """

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role == User.UserRole.EMPLOYEE
            and request.user.approval_status == User.ApprovalStatus.APPROVED
        )


class IsGuest(permissions.BasePermission):
    """
    Permission for Guest role:
    - Read-only access
    - Cannot view sensible information
    - Can only access own data, clients and perdcomps
    """

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role == User.UserRole.GUEST
            and request.user.approval_status == User.ApprovalStatus.APPROVED
            and request.method in permissions.SAFE_METHODS
        )


class IsAdmin(permissions.BasePermission):
    """
    Permission for Admin role:
    - Can view all logs
    - Can approve requests
    - Can change sensible data
    - Full access to the system
    """

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role == User.UserRole.ADMIN
            and request.user.approval_status == User.ApprovalStatus.APPROVED
        )


class IsEmployeeOrAdmin(permissions.BasePermission):
    """
    Permission for Employee or Admin roles
    """

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role in [User.UserRole.EMPLOYEE, User.UserRole.ADMIN]
            and request.user.approval_status == User.ApprovalStatus.APPROVED
        )


class IsOwnerOrAdmin(permissions.BasePermission):
    """
    Permission to allow users to edit their own data or admins to edit any data
    """

    def has_object_permission(self, request, view, obj):
        # Admin can access everything
        if (
            request.user.role == User.UserRole.ADMIN
            and request.user.approval_status == User.ApprovalStatus.APPROVED
        ):
            return True

        # Users can only access their own data
        if hasattr(obj, "user"):
            return obj.user == request.user
        elif hasattr(obj, "id"):
            return obj.id == request.user.id

        return False


class CanViewSensibleData(permissions.BasePermission):
    """
    Permission to view sensible data - only Admins
    """

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role == User.UserRole.ADMIN
            and request.user.approval_status == User.ApprovalStatus.APPROVED
        )


class CanChangeSensibleData(permissions.BasePermission):
    """
    Permission to change sensible data - only Admins
    """

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role == User.UserRole.ADMIN
            and request.user.approval_status == User.ApprovalStatus.APPROVED
            and request.method in ["POST", "PUT", "PATCH", "DELETE"]
        )


# Define your custom permissions here
