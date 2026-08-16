from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser
from rest_framework.authtoken.models import Token


class TokenProvisioner:
    """Creates/looks up DRF auth tokens for username-identified API clients."""

    INGEST_CLIENT_USERNAME = "ingest-client"

    @staticmethod
    def get_or_create_token(username: str) -> Token:
        """Get or create a user with the given username, and its auth token.

        get_user_model() is untyped for Pyright without django-stubs' mypy
        plugin; AbstractUser is the concrete shape Django's default objects
        manager gives us.
        """

        user_model: type[AbstractUser] = get_user_model()  # pyright: ignore[reportAssignmentType]
        user, _ = user_model.objects.get_or_create(username=username)
        token, _ = Token.objects.get_or_create(user=user)
        return token

    @classmethod
    def ensure_ingest_client_token(cls) -> Token:
        """Ensure the shared "ingest-client" user + token exist, for device-payload auth."""

        return cls.get_or_create_token(cls.INGEST_CLIENT_USERNAME)

    @classmethod
    def get_ingest_client_auth_key(cls) -> str:
        """Ensure the shared "ingest-client" user + token exist, and return the token's key."""

        return cls.ensure_ingest_client_token().key


class AdminUserProvisioner:  # pylint: disable=too-few-public-methods
    """Creates/looks up a Django admin (superuser) account.

    Single-purpose command object: one operation (get_or_create_admin_user),
    on purpose.
    """

    DEFAULT_ADMIN_USERNAME = "iot-admin"
    # TODO: support a real password-reset flow instead of a fixed default
    # password — this is a bootstrapping convenience for local/dev use.
    DEFAULT_ADMIN_PASSWORD = "ResetMe123!"

    @classmethod
    def get_or_create_admin_user(cls, username: str | None = None) -> tuple[AbstractUser, bool]:
        """Get or create a superuser with the given username, or DEFAULT_ADMIN_USERNAME if None.

        Only sets the password and staff/superuser flags at creation time —
        an existing admin's password and flags are left untouched on repeat
        calls, so re-running this never silently resets a real admin's
        credentials back to the default.
        """

        user_model: type[AbstractUser] = get_user_model()  # pyright: ignore[reportAssignmentType]
        user, created = user_model.objects.get_or_create(
            username=username or cls.DEFAULT_ADMIN_USERNAME,
            defaults={"is_staff": True, "is_superuser": True},
        )
        if created:
            user.set_password(cls.DEFAULT_ADMIN_PASSWORD)
            user.save()

        return user, created
