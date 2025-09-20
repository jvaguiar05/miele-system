from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.db import transaction
import getpass

User = get_user_model()


class Command(BaseCommand):
    help = "Create a superuser with specific role for Miele System"

    def add_arguments(self, parser):
        parser.add_argument("--username", type=str, help="Username for the superuser")
        parser.add_argument("--email", type=str, help="Email for the superuser")
        parser.add_argument(
            "--first-name", type=str, help="First name for the superuser"
        )
        parser.add_argument("--last-name", type=str, help="Last name for the superuser")
        parser.add_argument(
            "--role",
            type=str,
            choices=["admin", "employee", "guest"],
            default="admin",
            help="Role for the superuser (default: admin)",
        )
        parser.add_argument(
            "--password",
            type=str,
            help="Password for the superuser (if not provided, will prompt)",
        )
        parser.add_argument(
            "--no-input",
            action="store_true",
            help="Do not prompt for input (use provided arguments only)",
        )

    def handle(self, *args, **options):
        username = options.get("username")
        email = options.get("email")
        first_name = options.get("first_name")
        last_name = options.get("last_name")
        role = options.get("role")
        password = options.get("password")
        no_input = options.get("no_input")

        if not no_input:
            # Interactive mode
            if not username:
                username = input("Username: ")
            if not email:
                email = input("Email: ")
            if not first_name:
                first_name = input("First name: ")
            if not last_name:
                last_name = input("Last name: ")
            if not password:
                password = getpass.getpass("Password: ")
                password_confirm = getpass.getpass("Password (again): ")
                if password != password_confirm:
                    raise CommandError("Passwords do not match")

        # Validate required fields
        if not all([username, email, password]):
            raise CommandError("Username, email, and password are required")

        # Check if user already exists
        if User.objects.filter(username=username).exists():
            raise CommandError(f'User with username "{username}" already exists')

        if User.objects.filter(email=email).exists():
            raise CommandError(f'User with email "{email}" already exists')

        try:
            with transaction.atomic():
                # Create superuser with role
                user = User.objects.create_superuser(
                    username=username,
                    email=email,
                    password=password,
                    first_name=first_name or "",
                    last_name=last_name or "",
                    role=getattr(User.UserRole, role.upper()),
                    approval_status=User.ApprovalStatus.APPROVED,
                    is_active=True,
                    is_staff=True,
                )

                self.stdout.write(
                    self.style.SUCCESS(
                        f'Successfully created superuser "{username}" with role "{role}"'
                    )
                )

                # Display user information
                self.stdout.write(
                    self.style.WARNING(
                        f"User details:\n"
                        f"  Username: {user.username}\n"
                        f"  Email: {user.email}\n"
                        f"  Full name: {user.get_full_name()}\n"
                        f"  Role: {user.get_role_display()}\n"
                        f"  Approval status: {user.get_approval_status_display()}\n"
                        f"  Public ID: {user.public_id}\n"
                        f"  Is superuser: {user.is_superuser}\n"
                        f"  Is staff: {user.is_staff}"
                    )
                )

        except Exception as e:
            raise CommandError(f"Error creating superuser: {str(e)}")
