"""Punto 9 (el de mayor riesgo de esta ronda): gestión de usuarios del
tenant, ADMINISTRADOR exclusivo sin excepción (ni siquiera un Supervisor
pasa aquí), y la salvaguarda contra dejar un tenant sin ningún
administrador activo."""
from rest_framework import status
from rest_framework.test import APITestCase

from tenants.models import User, UserProfile
from tenants.tests.factories import create_branch, create_full_tenant, create_user_with_profile


class UserManagementPermissionBoundaryTests(APITestCase):
    def setUp(self):
        self.tenant = create_full_tenant(
            'Abarrotes Don Chuy', 'Centro', 'admin@donchuy.test', role=UserProfile.Role.ADMINISTRADOR,
        )
        self.cajero, self.cajero_profile = create_user_with_profile(
            'cajero@donchuy.test', self.tenant['branch'], capabilities={'handles_cash': True},
        )
        self.supervisor, _ = create_user_with_profile(
            'supervisor@donchuy.test', self.tenant['branch'], capabilities={'can_authorize_exceptions': True},
        )

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def test_administrador_can_list_users(self):
        self._auth(self.tenant['user'])
        response = self.client.get('/api/v1/user-profiles/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_supervisor_cannot_list_users(self):
        # "Sin excepción" es literal: a diferencia de reportes/inventario
        # (IsAdministratorOrSupervisor), gestión de usuarios NO tiene
        # excepción para Supervisor.
        self._auth(self.supervisor)
        response = self.client.get('/api/v1/user-profiles/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_plain_cajero_cannot_list_users(self):
        self._auth(self.cajero)
        response = self.client.get('/api/v1/user-profiles/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_any_authenticated_user_can_still_call_me(self):
        # El gate de administrador no debe romper el login normal de
        # nadie — /me/ sigue abierto a cualquier rol.
        self._auth(self.cajero)
        response = self.client.get('/api/v1/user-profiles/me/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], 'cajero@donchuy.test')

    def test_delete_is_disabled(self):
        # Nunca un DELETE genérico — todo cambio de activo/inactivo pasa
        # por deactivate/reactivate (ver services.deactivate_user).
        self._auth(self.tenant['user'])
        response = self.client.delete(f'/api/v1/user-profiles/{self.cajero_profile.id}/')
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class CreateTenantUserApiTests(APITestCase):
    def setUp(self):
        self.tenant_a = create_full_tenant(
            'Abarrotes Don Chuy', 'Centro', 'admin@donchuy.test', role=UserProfile.Role.ADMINISTRADOR,
        )
        self.tenant_b = create_full_tenant(
            'Papelería La Estrella', 'Norte', 'admin@estrella.test', role=UserProfile.Role.ADMINISTRADOR,
        )

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def test_administrador_can_create_a_user(self):
        self._auth(self.tenant_a['user'])
        response = self.client.post(
            '/api/v1/user-profiles/',
            {
                'email': 'nuevo@donchuy.test', 'password': 'ClaveSegura2026!',
                'branch': self.tenant_a['branch'].id, 'role': 'CAJERO', 'capabilities': {'handles_cash': True},
                'username': 'nuevo_cajero', 'date_of_birth': '1995-03-14',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['email'], 'nuevo@donchuy.test')
        self.assertEqual(response.data['username'], 'nuevo_cajero')
        self.assertTrue(response.data['is_active'])

        created_user = User.objects.get(email='nuevo@donchuy.test')
        self.assertTrue(created_user.check_password('ClaveSegura2026!'))
        self.assertEqual(created_user.username, 'nuevo_cajero')
        self.assertEqual(created_user.profile.date_of_birth.isoformat(), '1995-03-14')
        self.assertEqual(created_user.profile.company_id, self.tenant_a['company'].id)

    def test_cannot_create_a_user_pointing_to_another_tenants_branch(self):
        self._auth(self.tenant_a['user'])
        response = self.client.post(
            '/api/v1/user-profiles/',
            {
                'email': 'colado@donchuy.test', 'password': 'ClaveSegura2026!',
                'branch': self.tenant_b['branch'].id, 'role': 'CAJERO',
                'username': 'colado', 'date_of_birth': '1995-03-14',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.filter(email='colado@donchuy.test').exists())

    def test_rejects_duplicate_email_with_clean_400(self):
        self._auth(self.tenant_a['user'])
        response = self.client.post(
            '/api/v1/user-profiles/',
            {
                'email': 'admin@donchuy.test', 'password': 'ClaveSegura2026!',
                'branch': self.tenant_a['branch'].id, 'role': 'CAJERO',
                'username': 'otro_username', 'date_of_birth': '1995-03-14',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rejects_duplicate_username_with_clean_400(self):
        # Observación de sesión, punto 5: único a nivel SISTEMA, no solo
        # por tenant — se prueba contra un username ya usado en tenant_b.
        create_user_with_profile('otro-tenant@estrella.test', self.tenant_b['branch'], username='ya_existe')
        self._auth(self.tenant_a['user'])
        response = self.client.post(
            '/api/v1/user-profiles/',
            {
                'email': 'nuevo3@donchuy.test', 'password': 'ClaveSegura2026!',
                'branch': self.tenant_a['branch'].id, 'role': 'CAJERO',
                'username': 'ya_existe', 'date_of_birth': '1995-03-14',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.filter(email='nuevo3@donchuy.test').exists())

    def test_can_create_a_user_without_email(self):
        # Corrección de sesión: username es el único identificador
        # obligatorio, email es opcional.
        self._auth(self.tenant_a['user'])
        response = self.client.post(
            '/api/v1/user-profiles/',
            {
                'password': 'ClaveSegura2026!', 'branch': self.tenant_a['branch'].id, 'role': 'CAJERO',
                'username': 'solo_username',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertIsNone(response.data['email'])
        created_user = User.objects.get(username='solo_username')
        self.assertIsNone(created_user.email)
        self.assertTrue(created_user.check_password('ClaveSegura2026!'))

    def test_rejects_missing_username_with_clean_400(self):
        self._auth(self.tenant_a['user'])
        response = self.client.post(
            '/api/v1/user-profiles/',
            {
                'email': 'sinusuario@donchuy.test', 'password': 'ClaveSegura2026!',
                'branch': self.tenant_a['branch'].id, 'role': 'CAJERO',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.filter(email='sinusuario@donchuy.test').exists())

    def test_rejects_a_weak_password_with_clean_400(self):
        self._auth(self.tenant_a['user'])
        response = self.client.post(
            '/api/v1/user-profiles/',
            {
                'email': 'nuevo2@donchuy.test', 'password': '123456',
                'branch': self.tenant_a['branch'].id, 'role': 'CAJERO',
                'username': 'nuevo2', 'date_of_birth': '1995-03-14',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.filter(email='nuevo2@donchuy.test').exists())

    def test_supervisor_cannot_create_a_user(self):
        supervisor, _ = create_user_with_profile(
            'supervisor@donchuy.test', self.tenant_a['branch'], capabilities={'can_authorize_exceptions': True},
        )
        self._auth(supervisor)
        response = self.client.post(
            '/api/v1/user-profiles/',
            {
                'email': 'intento@donchuy.test', 'password': 'ClaveSegura2026!',
                'branch': self.tenant_a['branch'].id, 'role': 'CAJERO',
                'username': 'intento', 'date_of_birth': '1995-03-14',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class DeactivateUserSafeguardApiTests(APITestCase):
    """La pieza de mayor riesgo del punto 9: nunca dejar un tenant sin
    ningún administrador activo — probado tanto en el caso literal
    (auto-desactivación del último admin) como en el caso general
    (cualquiera intentando desactivar al último admin)."""

    def setUp(self):
        self.tenant = create_full_tenant(
            'Abarrotes Don Chuy', 'Centro', 'admin@donchuy.test', role=UserProfile.Role.ADMINISTRADOR,
        )
        self.cajero, self.cajero_profile = create_user_with_profile(
            'cajero@donchuy.test', self.tenant['branch'], capabilities={'handles_cash': True},
        )

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def test_administrador_can_deactivate_a_plain_cajero(self):
        self._auth(self.tenant['user'])
        response = self.client.post(f'/api/v1/user-profiles/{self.cajero_profile.id}/deactivate/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['is_active'])
        self.cajero.refresh_from_db()
        self.assertFalse(self.cajero.is_active)

    def test_the_last_active_admin_cannot_deactivate_themselves(self):
        admin_profile = self.tenant['profile']
        self._auth(self.tenant['user'])

        response = self.client.post(f'/api/v1/user-profiles/{admin_profile.id}/deactivate/')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('último administrador', response.data['detail'])
        self.tenant['user'].refresh_from_db()
        self.assertTrue(self.tenant['user'].is_active)

    def test_the_last_active_admin_cannot_be_deactivated_by_anyone_else(self):
        # Mismo riesgo, sin importar quién lo intente: un segundo admin
        # que desactiva al primero cuando es el ÚLTIMO activo debe
        # rechazarse igual que la auto-desactivación.
        second_admin, second_admin_profile = create_user_with_profile(
            'segundo-admin@donchuy.test', self.tenant['branch'], role=UserProfile.Role.ADMINISTRADOR,
        )
        admin_profile = self.tenant['profile']

        # Con dos admins activos, desactivar uno SÍ debe funcionar.
        self._auth(self.tenant['user'])
        first_response = self.client.post(f'/api/v1/user-profiles/{second_admin_profile.id}/deactivate/')
        self.assertEqual(first_response.status_code, status.HTTP_200_OK)

        # Ahora admin_profile es el único activo — intentar desactivarlo
        # (aunque sea otro admin quien lo pida) debe rechazarse.
        response = self.client.post(f'/api/v1/user-profiles/{admin_profile.id}/deactivate/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        admin_profile.user.refresh_from_db()
        self.assertTrue(admin_profile.user.is_active)

    def test_can_deactivate_an_admin_when_another_active_admin_remains(self):
        second_admin, second_admin_profile = create_user_with_profile(
            'segundo-admin@donchuy.test', self.tenant['branch'], role=UserProfile.Role.ADMINISTRADOR,
        )
        self._auth(self.tenant['user'])
        response = self.client.post(f'/api/v1/user-profiles/{second_admin_profile.id}/deactivate/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        second_admin.refresh_from_db()
        self.assertFalse(second_admin.is_active)

    def test_can_reactivate_a_deactivated_user(self):
        self._auth(self.tenant['user'])
        self.client.post(f'/api/v1/user-profiles/{self.cajero_profile.id}/deactivate/')

        response = self.client.post(f'/api/v1/user-profiles/{self.cajero_profile.id}/reactivate/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['is_active'])
        self.cajero.refresh_from_db()
        self.assertTrue(self.cajero.is_active)

    def test_cannot_deactivate_a_user_from_another_tenant(self):
        other_tenant = create_full_tenant(
            'Papelería La Estrella', 'Norte', 'admin@estrella.test', role=UserProfile.Role.ADMINISTRADOR,
        )
        other_cajero, other_cajero_profile = create_user_with_profile(
            'cajero@estrella.test', other_tenant['branch'],
        )

        self._auth(self.tenant['user'])
        response = self.client.post(f'/api/v1/user-profiles/{other_cajero_profile.id}/deactivate/')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        other_cajero.refresh_from_db()
        self.assertTrue(other_cajero.is_active)
