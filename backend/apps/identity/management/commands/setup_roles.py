from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.db import transaction

User = get_user_model()


class Command(BaseCommand):
    help = "Setup core application roles and permissions for Miele System"

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Reset all existing groups and permissions before creating new ones",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Display detailed information about operations",
        )

    def handle(self, *args, **options):
        reset = options.get("reset", False)
        verbose = options.get("verbose", False)

        if reset:
            self.stdout.write(
                self.style.WARNING("Resetting existing groups and permissions...")
            )
            Group.objects.all().delete()

        try:
            with transaction.atomic():
                self._create_role_groups(verbose)
                self._assign_permissions(verbose)
                self.stdout.write(
                    self.style.SUCCESS(
                        "Successfully setup core application roles and permissions"
                    )
                )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error setting up roles: {str(e)}"))

    def _create_role_groups(self, verbose):
        """Create Django groups for each user role"""
        roles = [
            ("Admin", "Full system access with administrative privileges"),
            ("Employee", "Standard user access with business operations"),
            ("Guest", "Limited read-only access to public information"),
        ]

        for role_name, description in roles:
            group, created = Group.objects.get_or_create(name=role_name)
            if created and verbose:
                self.stdout.write(f"Created group: {role_name} - {description}")
            elif verbose:
                self.stdout.write(f"Group already exists: {role_name}")

    def _assign_permissions(self, verbose):
        """Assign permissions to role groups"""

        # Get content types for our apps
        user_ct = ContentType.objects.get_for_model(User)

        # Get groups
        admin_group = Group.objects.get(name="Admin")
        employee_group = Group.objects.get(name="Employee")
        guest_group = Group.objects.get(name="Guest")

        # Admin permissions (full access)
        admin_permissions = [
            # User management
            "add_user",
            "change_user",
            "delete_user",
            "view_user",
            # System administration
            "can_access_admin",
            "can_manage_users",
            "can_approve_changes",
            "can_view_sensitive_data",
            "can_modify_sensitive_data",
            # Identity app permissions
            "can_create_change_requests",
            "can_approve_change_requests",
            "can_view_user_roles",
            "can_assign_roles",
        ]

        # Employee permissions (standard business operations)
        employee_permissions = [
            # Basic user operations
            "view_user",
            "change_user",  # Can view and edit their own profile
            # Business operations
            "can_view_business_data",
            "can_create_change_requests",
            "can_view_own_data",
        ]

        # Guest permissions (read-only access)
        guest_permissions = [
            # Limited read access
            "view_user",  # Can view their own profile only
            "can_view_public_data",
        ]

        # Create custom permissions if they don't exist
        custom_permissions = [
            ("can_access_admin", "Can access admin interface"),
            ("can_manage_users", "Can manage other users"),
            ("can_approve_changes", "Can approve change requests"),
            ("can_view_sensitive_data", "Can view sensitive user data"),
            ("can_modify_sensitive_data", "Can modify sensitive user data"),
            ("can_create_change_requests", "Can create change requests"),
            ("can_approve_change_requests", "Can approve change requests"),
            ("can_view_user_roles", "Can view user roles"),
            ("can_assign_roles", "Can assign roles to users"),
            ("can_view_business_data", "Can view business data"),
            ("can_view_own_data", "Can view own data"),
            ("can_view_public_data", "Can view public data"),
        ]

        for codename, name in custom_permissions:
            permission, created = Permission.objects.get_or_create(
                codename=codename, content_type=user_ct, defaults={"name": name}
            )
            if created and verbose:
                self.stdout.write(f"Created permission: {codename} - {name}")

        # Assign permissions to groups
        self._assign_permissions_to_group(
            admin_group, admin_permissions, verbose, "Admin"
        )
        self._assign_permissions_to_group(
            employee_group, employee_permissions, verbose, "Employee"
        )
        self._assign_permissions_to_group(
            guest_group, guest_permissions, verbose, "Guest"
        )

    def _assign_permissions_to_group(
        self, group, permission_codenames, verbose, group_name
    ):
        """Assign specific permissions to a group"""
        assigned_count = 0

        for codename in permission_codenames:
            try:
                permission = Permission.objects.get(codename=codename)
                group.permissions.add(permission)
                assigned_count += 1
                if verbose:
                    self.stdout.write(f"  Assigned {codename} to {group_name}")
            except Permission.DoesNotExist:
                if verbose:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  Permission {codename} not found, skipping"
                        )
                    )

        self.stdout.write(
            self.style.SUCCESS(
                f"Assigned {assigned_count} permissions to {group_name} group"
            )
        )

    def _display_role_summary(self):
        """Display a summary of created roles and their permissions"""
        self.stdout.write("\n" + "=" * 50)
        self.stdout.write("ROLE SUMMARY")
        self.stdout.write("=" * 50)

        for group in Group.objects.all():
            self.stdout.write(f"\n{group.name.upper()} ROLE:")
            permissions = group.permissions.all()
            if permissions:
                for perm in permissions:
                    self.stdout.write(f"  - {perm.codename}: {perm.name}")
            else:
                self.stdout.write("  - No permissions assigned")

        self.stdout.write("\n" + "=" * 50)
