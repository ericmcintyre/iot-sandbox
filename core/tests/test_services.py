from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token

from core.services import AdminUserProvisioner, TokenProvisioner
from core.tests.utils import BaseAPITestCase


class TestGetOrCreateToken(BaseAPITestCase):
    def test_creates_a_user_and_token_for_a_new_username(self):
        """An unseen username should get both a new User and a new Token."""

        token = TokenProvisioner.get_or_create_token("new-client")

        self.assertEqual(token.user.username, "new-client")
        self.assertEqual(Token.objects.filter(user__username="new-client").count(), 1)

    def test_reuses_the_existing_token_for_a_known_username(self):
        """Calling it again with the same username should return the same token, not a new one."""

        first = TokenProvisioner.get_or_create_token("existing-client")
        second = TokenProvisioner.get_or_create_token("existing-client")

        self.assertEqual(first.key, second.key)
        self.assertEqual(get_user_model().objects.filter(username="existing-client").count(), 1)


class TestEnsureIngestClientToken(BaseAPITestCase):
    def test_creates_the_ingest_client_user(self):
        """It should provision a user literally named "ingest-client"."""

        token = TokenProvisioner.ensure_ingest_client_token()

        self.assertEqual(token.user.username, "ingest-client")

    def test_is_idempotent(self):
        """Calling it twice should return the same token rather than creating a second one."""

        first = TokenProvisioner.ensure_ingest_client_token()
        second = TokenProvisioner.ensure_ingest_client_token()

        self.assertEqual(first.key, second.key)
        self.assertEqual(get_user_model().objects.filter(username="ingest-client").count(), 1)


class TestGetIngestClientAuthKey(BaseAPITestCase):
    def test_is_idempotent(self):
        """Calling it twice should return the same key rather than creating a second token."""

        first = TokenProvisioner.get_ingest_client_auth_key()
        second = TokenProvisioner.get_ingest_client_auth_key()

        self.assertEqual(first, second)
        self.assertEqual(get_user_model().objects.filter(username="ingest-client").count(), 1)


class TestGetOrCreateAdminUser(BaseAPITestCase):
    def test_creates_a_superuser_with_the_default_username(self):
        """No username given should provision AdminUserProvisioner.DEFAULT_ADMIN_USERNAME."""

        user, created = AdminUserProvisioner.get_or_create_admin_user()

        self.assertTrue(created)
        self.assertEqual(user.username, AdminUserProvisioner.DEFAULT_ADMIN_USERNAME)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.check_password(AdminUserProvisioner.DEFAULT_ADMIN_PASSWORD))

    def test_creates_a_superuser_with_a_given_username(self):
        """An explicit username should override the default."""

        user, created = AdminUserProvisioner.get_or_create_admin_user("custom-admin")

        self.assertTrue(created)
        self.assertEqual(user.username, "custom-admin")

    def test_does_not_reset_an_existing_admins_password_or_flags(self):
        """Calling it again for an existing user should leave their password/flags untouched."""

        user, _ = AdminUserProvisioner.get_or_create_admin_user()
        user.set_password("something-else-entirely")
        user.is_superuser = False
        user.save()

        same_user, created = AdminUserProvisioner.get_or_create_admin_user()

        self.assertFalse(created)
        self.assertEqual(same_user.pk, user.pk)
        self.assertTrue(same_user.check_password("something-else-entirely"))
        self.assertFalse(same_user.is_superuser)
