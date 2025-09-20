from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction
from django.db.models import Q

User = get_user_model()


class Command(BaseCommand):
    help = "Migrate existing users to the new role-based system"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be done without making changes",
        )
        parser.add_argument(
            "--default-role",
            type=str,
            choices=["admin", "employee", "guest"],
            default="employee",
            help="Default role for users without explicit roles (default: employee)",
        )
        parser.add_argument(
            "--auto-approve",
            action="store_true",
            help="Automatically approve all migrated users",
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)
        default_role = options.get("default_role", "employee")
        auto_approve = options.get("auto_approve", False)

        if dry_run:
            self.stdout.write(
                self.style.WARNING("DRY RUN MODE - No changes will be made")
            )

        try:
            # Get all users that need migration
            users_to_migrate = self._get_users_to_migrate()

            if not users_to_migrate:
                self.stdout.write(self.style.SUCCESS("No users need migration"))
                return

            self.stdout.write(f"Found {len(users_to_migrate)} users to migrate")

            if not dry_run:
                with transaction.atomic():
                    self._migrate_users(users_to_migrate, default_role, auto_approve)
            else:
                self._show_migration_preview(
                    users_to_migrate, default_role, auto_approve
                )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error during migration: {str(e)}"))

    def _get_users_to_migrate(self):
        """Get users that need migration to the new role system"""
        # Users without a role or with pending approval status
        return User.objects.filter(
            Q(role__isnull=True) | Q(approval_status=User.ApprovalStatus.PENDING)
        )

    def _migrate_users(self, users, default_role, auto_approve):
        """Migrate users to the new role system"""
        migrated_count = 0

        # Get role groups
        groups = {
            "admin": Group.objects.get(name="Admin"),
            "employee": Group.objects.get(name="Employee"),
            "guest": Group.objects.get(name="Guest"),
        }

        for user in users:
            # Determine user role based on existing permissions
            role = self._determine_user_role(user, default_role)

            # Update user role
            if not user.role:
                user.role = getattr(User.UserRole, role.upper())

            # Update approval status if needed
            if auto_approve and user.approval_status == User.ApprovalStatus.PENDING:
                user.approval_status = User.ApprovalStatus.APPROVED

            # Ensure active users have proper approval status
            if user.is_active and user.approval_status == User.ApprovalStatus.PENDING:
                user.approval_status = User.ApprovalStatus.APPROVED

            user.save()

            # Add user to appropriate group
            user.groups.add(groups[role])

            migrated_count += 1

            self.stdout.write(f"Migrated user: {user.username} -> {role} role")

        self.stdout.write(
            self.style.SUCCESS(f"Successfully migrated {migrated_count} users")
        )

    def _show_migration_preview(self, users, default_role, auto_approve):
        """Show what would be migrated without making changes"""
        self.stdout.write("\nMIGRATION PREVIEW:")
        self.stdout.write("-" * 40)

        for user in users:
            role = self._determine_user_role(user, default_role)
            current_status = (
                user.get_approval_status_display()
                if hasattr(user, "approval_status")
                else "Unknown"
            )
            new_status = "Approved" if auto_approve else current_status

            self.stdout.write(
                f"User: {user.username}\n"
                f'  Current role: {getattr(user, "role", "None")}\n'
                f"  New role: {role}\n"
                f"  Current status: {current_status}\n"
                f"  New status: {new_status}\n"
                f"  Is superuser: {user.is_superuser}\n"
                f"  Is staff: {user.is_staff}\n"
                "-" * 40
            )

    def _determine_user_role(self, user, default_role):
        """Determine appropriate role for a user based on existing permissions"""

        # Superusers become admins
        if user.is_superuser:
            return "admin"

        # Staff users become employees by default
        if user.is_staff:
            return "employee"

        # Check if user has admin-like permissions
        if user.user_permissions.filter(
            codename__in=["add_user", "change_user", "delete_user"]
        ).exists():
            return "admin"

        # Check if user is in admin groups
        if user.groups.filter(name__icontains="admin").exists():
            return "admin"

        # Check if user is in employee/staff groups
        if user.groups.filter(name__icontains="employee").exists():
            return "employee"

        # Default role
        return default_role

    def _display_migration_summary(self):
        """Display summary of migration results"""
        self.stdout.write("\n" + "=" * 50)
        self.stdout.write("MIGRATION SUMMARY")
        self.stdout.write("=" * 50)

        # Count users by role
        role_counts = {}
        for role in User.UserRole:
            count = User.objects.filter(role=role).count()
            role_counts[role.label] = count

        for role, count in role_counts.items():
            self.stdout.write(f"{role}: {count} users")

        # Count by approval status
        self.stdout.write("\nApproval Status:")
        for status in User.ApprovalStatus:
            count = User.objects.filter(approval_status=status).count()
            self.stdout.write(f"{status.label}: {count} users")

        self.stdout.write("\n" + "=" * 50)
