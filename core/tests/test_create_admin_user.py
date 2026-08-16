import io

from django.contrib.auth import get_user_model
from django.core.management import call_command

from core.services import AdminUserProvisioner
from core.tests.utils import BaseAPITestCase


class TestCreateAdminUserCommand(BaseAPITestCase):
    def test_creates_the_default_admin_user_with_no_arguments(self):
        """Running with no --username should provision AdminUserProvisioner's default username."""

        call_command("create_admin_user", stdout=io.StringIO())

        self.assertTrue(
            get_user_model()
            .objects.filter(username=AdminUserProvisioner.DEFAULT_ADMIN_USERNAME, is_superuser=True)
            .exists()
        )

    def test_creates_a_custom_username_when_given(self):
        """--username should override the default."""

        call_command("create_admin_user", username="custom-admin", stdout=io.StringIO())

        self.assertTrue(get_user_model().objects.filter(username="custom-admin").exists())

    def test_is_safe_to_run_twice(self):
        """Re-running the command shouldn't create a duplicate user or error."""

        call_command("create_admin_user", stdout=io.StringIO())
        call_command("create_admin_user", stdout=io.StringIO())

        self.assertEqual(
            get_user_model()
            .objects.filter(username=AdminUserProvisioner.DEFAULT_ADMIN_USERNAME)
            .count(),
            1,
        )
