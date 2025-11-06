# Create a user without admin privileges. But active in the system.
# This user can be used for testing API access with normal user permissions.

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = "Create a non-admin test user."

    def handle(self, *args, **kwargs):
        username = "pocador"
        email = "jvads2005@gmail.com"
        user = User.objects.create_user(
            username=username, email=email, password="caraiconasas"
        )
        user.is_active = True
        user.is_staff = False
        user.approval_status = "approved"
        user.save()
        self.stdout.write(
            self.style.SUCCESS(f"Test user '{username}' created successfully.")
        )
        self.stdout.write(self.style.WARNING("Username: pocador"))
        self.stdout.write(self.style.WARNING("Password: caraiconasas"))
        self.stdout.write(
            self.style.WARNING(
                "Use this user for testing API access with normal user permissions."
            )
        )
