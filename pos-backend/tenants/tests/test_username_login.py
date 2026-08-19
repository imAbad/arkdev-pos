"""Observación de sesión, punto 5: login alterno de mostrador (username +
fecha de nacimiento). email+contraseña (tenants/tests/test_auth.py) sigue
funcionando exactamente igual — se prueba explícitamente que no hay
regresión ahí."""
from datetime import date

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from tenants.models import User, UserProfile
from tenants.services import UsernameLoginError, request_username_login
from tenants.tests.factories import create_branch, create_company, create_user_with_profile


class UsernameUniquenessModelTests(TestCase):
    def test_username_is_unique_across_different_tenants(self):
        # El mismo riesgo que ya se evitó con email (decisiones_post_
        # auditoria.md §5) — username también es único a nivel SISTEMA,
        # no por tenant, a propósito.
        company_a = create_company('Abarrotes Don Chuy')
        branch_a = create_branch(company_a)
        company_b = create_company('Papelería La Estrella')
        branch_b = create_branch(company_b)

        create_user_with_profile('a@donchuy.test', branch_a, username='cajero1')
        with self.assertRaises(Exception):
            create_user_with_profile('b@estrella.test', branch_b, username='cajero1')

    def test_multiple_users_can_have_no_username(self):
        # unique=True + null=True: varios NULL no chocan entre sí.
        company = create_company('Abarrotes Don Chuy')
        branch = create_branch(company)
        create_user_with_profile('a@donchuy.test', branch)
        create_user_with_profile('b@donchuy.test', branch)
        self.assertEqual(User.objects.filter(username__isnull=True).count(), 2)


class RequestUsernameLoginServiceTests(TestCase):
    def setUp(self):
        self.company = create_company('Abarrotes Don Chuy')
        self.branch = create_branch(self.company)

    def test_correct_username_and_date_of_birth_succeeds(self):
        user, _ = create_user_with_profile(
            'cajero@donchuy.test', self.branch, username='cajero1', date_of_birth=date(1998, 6, 20),
        )
        result = request_username_login(username='cajero1', date_of_birth=date(1998, 6, 20))
        self.assertEqual(result, user)

    def test_username_lookup_is_case_insensitive(self):
        user, _ = create_user_with_profile(
            'cajero@donchuy.test', self.branch, username='Cajero1', date_of_birth=date(1998, 6, 20),
        )
        result = request_username_login(username='cajero1', date_of_birth=date(1998, 6, 20))
        self.assertEqual(result, user)

    def test_wrong_date_of_birth_is_rejected(self):
        create_user_with_profile(
            'cajero@donchuy.test', self.branch, username='cajero1', date_of_birth=date(1998, 6, 20),
        )
        with self.assertRaises(UsernameLoginError):
            request_username_login(username='cajero1', date_of_birth=date(2000, 1, 1))

    def test_nonexistent_username_is_rejected(self):
        with self.assertRaises(UsernameLoginError):
            request_username_login(username='no-existe', date_of_birth=date(1998, 6, 20))

    def test_user_without_a_date_of_birth_set_cannot_log_in_this_way(self):
        create_user_with_profile('cajero@donchuy.test', self.branch, username='cajero1')
        with self.assertRaises(UsernameLoginError):
            request_username_login(username='cajero1', date_of_birth=date(1998, 6, 20))

    def test_inactive_user_is_rejected(self):
        user, _ = create_user_with_profile(
            'cajero@donchuy.test', self.branch, username='cajero1', date_of_birth=date(1998, 6, 20),
        )
        user.is_active = False
        user.save(update_fields=['is_active'])
        with self.assertRaises(UsernameLoginError):
            request_username_login(username='cajero1', date_of_birth=date(1998, 6, 20))


class UsernameLoginApiTests(APITestCase):
    def setUp(self):
        self.company = create_company('Abarrotes Don Chuy')
        self.branch = create_branch(self.company)
        self.user, self.profile = create_user_with_profile(
            'cajero@donchuy.test', self.branch, username='cajero1', date_of_birth=date(1998, 6, 20),
        )

    def test_successful_login_returns_the_same_token_shape_as_email_login(self):
        response = self.client.post(
            '/api/v1/auth/token/username/', {'username': 'cajero1', 'date_of_birth': '1998-06-20'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)

    def test_the_issued_token_authenticates_like_a_normal_login(self):
        login_response = self.client.post(
            '/api/v1/auth/token/username/', {'username': 'cajero1', 'date_of_birth': '1998-06-20'}, format='json',
        )
        access = login_response.data['access']
        response = self.client.get('/api/v1/user-profiles/me/', HTTP_AUTHORIZATION=f'Bearer {access}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], 'cajero@donchuy.test')

    def test_wrong_date_of_birth_returns_a_clean_401(self):
        response = self.client.post(
            '/api/v1/auth/token/username/', {'username': 'cajero1', 'date_of_birth': '2000-01-01'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data['detail'], 'Usuario o fecha de nacimiento incorrectos.')

    def test_nonexistent_username_returns_a_clean_401_not_a_500(self):
        response = self.client.post(
            '/api/v1/auth/token/username/', {'username': 'no-existe', 'date_of_birth': '1998-06-20'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class EmailLoginStillWorksTests(APITestCase):
    """Sin regresión: email+contraseña sigue siendo el login real, sin
    ningún cambio de comportamiento."""

    def setUp(self):
        self.company = create_company('Abarrotes Don Chuy')
        self.branch = create_branch(self.company)
        self.user, _ = create_user_with_profile(
            'cajero@donchuy.test', self.branch, username='cajero1',
            date_of_birth=date(1998, 6, 20), password='ClaveSegura2026!',
        )

    def test_email_and_password_login_unaffected(self):
        response = self.client.post(
            '/api/v1/auth/token/', {'email': 'cajero@donchuy.test', 'password': 'ClaveSegura2026!'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
