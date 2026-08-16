from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient
from test_plus.test import APITestCase


class BaseAPITestCase(APITestCase):
    """Shared base for DRF endpoint tests: DRF's APIClient plus a token-auth helper."""

    client: APIClient

    def authenticate(self, username="test-client") -> AbstractUser:
        """Create a user + token and attach it to self.client for subsequent requests.

        get_user_model() is untyped for Pyright without django-stubs' mypy
        plugin; AbstractUser is the concrete shape Django's default
        create_user()/objects give us.
        """

        user_model: type[AbstractUser] = get_user_model()  # pyright: ignore[reportAssignmentType]
        user = user_model.objects.create_user(username=username, password="unused")
        token = Token.objects.create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        return user
