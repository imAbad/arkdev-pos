from django.contrib.auth import authenticate, get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from tenants.tests.factories import create_branch, create_company

User = get_user_model()


class EmailLoginModelTests(TestCase):
    def test_username_field_is_email(self):
        # USERNAME_FIELD='email' se mantiene por plomería interna de
        # Django (createsuperuser, ModelBackend, admin) — no determina
        # qué acepta el login real de la API. `username` existe como
        # campo propio, único a nivel sistema, distinto del username de
        # AbstractUser que colisionaba entre tenants en pharma_core (ver
        # tenants.models.User, docstring completo) — el login real acepta
        # username O email indistintamente (ver TokenLoginApiTests).
        self.assertEqual(User.USERNAME_FIELD, 'email')
        field_names = [f.name for f in User._meta.get_fields()]
        self.assertIn('username', field_names)

    def test_two_tenants_can_reuse_the_same_local_part(self):
        # El bug original en pharma_core: dos tenants no podían tener ambos
        # un usuario "cajero1" porque username era único globalmente.
        # Con email, cada dirección ya es única de por sí y no hay colisión
        # de "identidad visual" entre tenants (cajero@donchuy.test vs.
        # cajero@estrella.test conviven sin problema).
        User.objects.create_user(email='cajero@donchuy.test', password='testpass123')
        User.objects.create_user(email='cajero@estrella.test', password='testpass123')
        self.assertEqual(User.objects.count(), 2)

    def test_authenticate_with_email_and_password(self):
        User.objects.create_user(email='admin@donchuy.test', password='testpass123')
        user = authenticate(email='admin@donchuy.test', password='testpass123')
        self.assertIsNotNone(user)

    def test_authenticate_fails_with_wrong_password(self):
        User.objects.create_user(email='admin@donchuy.test', password='testpass123')
        user = authenticate(email='admin@donchuy.test', password='wrong')
        self.assertIsNone(user)

    def test_email_must_be_unique(self):
        User.objects.create_user(email='dup@donchuy.test', password='testpass123')
        with self.assertRaises(Exception):
            User.objects.create_user(email='dup@donchuy.test', password='testpass123')


class TokenLoginApiTests(APITestCase):
    """Un solo endpoint de login (`IdentifierTokenObtainPairSerializer`)
    que acepta `username` o `email` como identificador — misma cuenta,
    misma contraseña, sin distinguir el "modo" en ningún lado más que en
    qué valor se manda como `identifier`."""

    def setUp(self):
        self.company = create_company('Abarrotes Don Chuy')
        self.branch = create_branch(self.company)
        self.user = User.objects.create_user(
            email='admin@donchuy.test', password='testpass123', username='admin_donchuy',
        )

    def _login(self, identifier, password):
        return self.client.post(
            '/api/v1/auth/token/', {'identifier': identifier, 'password': password}, format='json',
        )

    def test_obtain_token_with_email(self):
        response = self._login('admin@donchuy.test', 'testpass123')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)

    def test_obtain_token_with_username(self):
        # Mismo password que el login por email arriba — es la MISMA
        # cuenta, no un mecanismo de auth distinto.
        response = self._login('admin_donchuy', 'testpass123')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)

    def test_username_login_is_case_insensitive(self):
        response = self._login('ADMIN_DONCHUY', 'testpass123')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_obtain_token_rejects_wrong_password_by_email(self):
        response = self._login('admin@donchuy.test', 'wrong')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_obtain_token_rejects_wrong_password_by_username(self):
        response = self._login('admin_donchuy', 'wrong')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_obtain_token_rejects_unknown_identifier(self):
        response = self._login('no_existe', 'testpass123')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_obtain_token_rejects_inactive_user(self):
        self.user.is_active = False
        self.user.save(update_fields=['is_active'])
        response = self._login('admin_donchuy', 'testpass123')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_access_token_authorizes_scoped_request(self):
        token_response = self._login('admin@donchuy.test', 'testpass123')
        access = token_response.data['access']
        response = self.client.get(
            '/api/v1/branches/',
            HTTP_AUTHORIZATION=f'Bearer {access}',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class EmailOptionalAtAccountLevelTests(APITestCase):
    """Corrección de sesión: username es el único identificador
    obligatorio — email puede faltar por completo y la cuenta sigue
    siendo utilizable de punta a punta (crear, entrar, y ninguna falla
    de serialización por email=None)."""

    def test_can_create_and_authenticate_a_user_without_email(self):
        user = User.objects.create_user(password='testpass123', username='solo_username')
        self.assertIsNone(user.email)
        response = self.client.post(
            '/api/v1/auth/token/', {'identifier': 'solo_username', 'password': 'testpass123'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
