from django.contrib.auth import authenticate, get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from tenants.tests.factories import create_branch, create_company

User = get_user_model()


class EmailLoginModelTests(TestCase):
    def test_username_field_is_email(self):
        self.assertEqual(User.USERNAME_FIELD, 'email')
        field_names = [f.name for f in User._meta.get_fields()]
        self.assertNotIn('username', field_names)

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
    def setUp(self):
        self.company = create_company('Abarrotes Don Chuy')
        self.branch = create_branch(self.company)
        self.user = User.objects.create_user(email='admin@donchuy.test', password='testpass123')

    def test_obtain_token_with_email(self):
        response = self.client.post(
            '/api/v1/auth/token/',
            {'email': 'admin@donchuy.test', 'password': 'testpass123'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)

    def test_obtain_token_rejects_wrong_password(self):
        response = self.client.post(
            '/api/v1/auth/token/',
            {'email': 'admin@donchuy.test', 'password': 'wrong'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_access_token_authorizes_scoped_request(self):
        token_response = self.client.post(
            '/api/v1/auth/token/',
            {'email': 'admin@donchuy.test', 'password': 'testpass123'},
            format='json',
        )
        access = token_response.data['access']
        response = self.client.get(
            '/api/v1/branches/',
            HTTP_AUTHORIZATION=f'Bearer {access}',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
