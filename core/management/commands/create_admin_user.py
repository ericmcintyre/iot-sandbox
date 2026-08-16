from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from core.services import AdminUserProvisioner


class Command(BaseCommand):
    help = "Get or create the admin (superuser) account, via AdminUserProvisioner."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--username",
            default=None,
            help=f"Defaults to {AdminUserProvisioner.DEFAULT_ADMIN_USERNAME!r} if omitted.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        user, created = AdminUserProvisioner.get_or_create_admin_user(options["username"])

        if created:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Created admin user {user.username!r} "
                    f"(password: {AdminUserProvisioner.DEFAULT_ADMIN_PASSWORD!r})"
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS(f"Admin user {user.username!r} already exists."))
