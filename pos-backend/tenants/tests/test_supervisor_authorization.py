"""PIN/reautenticación para can_authorize_exceptions (punto 6). Mismo
estándar pedido: intentos fallidos, expiración, y que quede en AuditLog
quién autorizó qué — no solo el happy path."""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from audit.models import AuditLog
from tenants.models import SupervisorAuthorization, UserProfile
from tenants.services import AuthorizationError, consume_supervisor_authorization, request_supervisor_authorization
from tenants.tests.factories import create_full_tenant, create_user_with_profile


class RequestSupervisorAuthorizationTests(TestCase):
    def setUp(self):
        self.tenant = create_full_tenant('Abarrotes Don Chuy', 'Centro', 'cajero@donchuy.test')

    def test_administrador_can_authorize(self):
        admin, _ = create_user_with_profile(
            'admin@donchuy.test', self.tenant['branch'], role=UserProfile.Role.ADMINISTRADOR,
        )
        authorization = request_supervisor_authorization(
            requesting_user=self.tenant['user'], email=admin.email, password='testpass123', reason='descuento',
        )
        self.assertEqual(authorization.supervisor, admin)
        self.assertEqual(authorization.requested_by, self.tenant['user'])
        self.assertEqual(authorization.reason, 'descuento')
        self.assertFalse(authorization.is_used)
        self.assertFalse(authorization.is_expired)

    def test_cajero_with_can_authorize_exceptions_can_authorize(self):
        # Supervisor = CAJERO + capability, no un role aparte.
        supervisor, _ = create_user_with_profile(
            'supervisor@donchuy.test', self.tenant['branch'],
            role=UserProfile.Role.CAJERO, capabilities={'can_authorize_exceptions': True},
        )
        authorization = request_supervisor_authorization(
            requesting_user=self.tenant['user'], email=supervisor.email, password='testpass123',
        )
        self.assertEqual(authorization.supervisor, supervisor)

    def test_plain_cajero_without_capability_is_rejected(self):
        other_cajero, _ = create_user_with_profile('otro@donchuy.test', self.tenant['branch'])
        with self.assertRaises(AuthorizationError):
            request_supervisor_authorization(
                requesting_user=self.tenant['user'], email=other_cajero.email, password='testpass123',
            )
        self.assertEqual(SupervisorAuthorization.objects.count(), 0)

    def test_wrong_password_is_rejected(self):
        admin, _ = create_user_with_profile(
            'admin@donchuy.test', self.tenant['branch'], role=UserProfile.Role.ADMINISTRADOR,
        )
        with self.assertRaises(AuthorizationError):
            request_supervisor_authorization(
                requesting_user=self.tenant['user'], email=admin.email, password='wrong-password',
            )
        self.assertEqual(SupervisorAuthorization.objects.count(), 0)

    def test_nonexistent_supervisor_email_is_rejected(self):
        with self.assertRaises(AuthorizationError):
            request_supervisor_authorization(
                requesting_user=self.tenant['user'], email='no-existe@donchuy.test', password='cualquiera',
            )
        self.assertEqual(SupervisorAuthorization.objects.count(), 0)

    def test_supervisor_from_another_tenant_is_rejected(self):
        other_tenant = create_full_tenant(
            'Papelería La Estrella', 'Norte', 'admin@estrella.test', role=UserProfile.Role.ADMINISTRADOR,
        )
        with self.assertRaises(AuthorizationError):
            request_supervisor_authorization(
                requesting_user=self.tenant['user'],
                email=other_tenant['user'].email, password='testpass123',
            )
        self.assertEqual(SupervisorAuthorization.objects.count(), 0)

    def test_requesting_user_without_profile_is_rejected(self):
        from tenants.models import User
        orphan = User.objects.create_user(email='sinprofile@test.com', password='x')
        admin, _ = create_user_with_profile(
            'admin@donchuy.test', self.tenant['branch'], role=UserProfile.Role.ADMINISTRADOR,
        )
        with self.assertRaises(AuthorizationError):
            request_supervisor_authorization(requesting_user=orphan, email=admin.email, password='testpass123')

    def test_expires_at_respects_configured_ttl(self):
        from django.conf import settings

        admin, _ = create_user_with_profile(
            'admin@donchuy.test', self.tenant['branch'], role=UserProfile.Role.ADMINISTRADOR,
        )
        before = timezone.now()
        authorization = request_supervisor_authorization(
            requesting_user=self.tenant['user'], email=admin.email, password='testpass123',
        )
        expected = before + timedelta(minutes=settings.SUPERVISOR_AUTHORIZATION_TTL_MINUTES)
        self.assertAlmostEqual(authorization.expires_at, expected, delta=timedelta(seconds=5))

    def test_two_requests_get_different_tokens(self):
        admin, _ = create_user_with_profile(
            'admin@donchuy.test', self.tenant['branch'], role=UserProfile.Role.ADMINISTRADOR,
        )
        first = request_supervisor_authorization(
            requesting_user=self.tenant['user'], email=admin.email, password='testpass123',
        )
        second = request_supervisor_authorization(
            requesting_user=self.tenant['user'], email=admin.email, password='testpass123',
        )
        self.assertNotEqual(first.token, second.token)


class SupervisorAuthorizationAuditTests(TestCase):
    """El pedido explícito: quién autorizó qué queda en AuditLog."""

    def setUp(self):
        self.tenant = create_full_tenant('Abarrotes Don Chuy', 'Centro', 'cajero@donchuy.test')
        self.admin, _ = create_user_with_profile(
            'admin@donchuy.test', self.tenant['branch'], role=UserProfile.Role.ADMINISTRADOR,
        )

    def test_successful_grant_is_logged_with_supervisor_as_actor(self):
        request_supervisor_authorization(
            requesting_user=self.tenant['user'], email=self.admin.email, password='testpass123',
            reason='descuento fuera de política',
        )
        entry = AuditLog.objects.get(action='supervisor_authorization.granted')
        self.assertEqual(entry.user, self.admin)
        self.assertEqual(entry.changes['requested_by'], self.tenant['user'].email)
        self.assertEqual(entry.changes['reason'], 'descuento fuera de política')

    def test_failed_attempt_is_logged_with_requesting_user_as_actor(self):
        with self.assertRaises(AuthorizationError):
            request_supervisor_authorization(
                requesting_user=self.tenant['user'], email=self.admin.email, password='wrong',
            )
        entry = AuditLog.objects.get(action='supervisor_authorization.denied')
        self.assertEqual(entry.user, self.tenant['user'])
        self.assertEqual(entry.changes['reason_code'], 'invalid_credentials')

    def test_insufficient_capability_attempt_is_logged_with_reason_code(self):
        other_cajero, _ = create_user_with_profile('otro@donchuy.test', self.tenant['branch'])
        with self.assertRaises(AuthorizationError):
            request_supervisor_authorization(
                requesting_user=self.tenant['user'], email=other_cajero.email, password='testpass123',
            )
        entry = AuditLog.objects.get(action='supervisor_authorization.denied')
        self.assertEqual(entry.changes['reason_code'], 'insufficient_capability')

    def test_consumption_is_logged(self):
        authorization = request_supervisor_authorization(
            requesting_user=self.tenant['user'], email=self.admin.email, password='testpass123',
        )
        consume_supervisor_authorization(token=authorization.token, consuming_user=self.tenant['user'])
        entry = AuditLog.objects.get(action='supervisor_authorization.consumed')
        self.assertEqual(entry.user, self.tenant['user'])
        self.assertEqual(entry.changes['supervisor'], self.admin.email)


class ConsumeSupervisorAuthorizationTests(TestCase):
    def setUp(self):
        self.tenant = create_full_tenant('Abarrotes Don Chuy', 'Centro', 'cajero@donchuy.test')
        self.admin, _ = create_user_with_profile(
            'admin@donchuy.test', self.tenant['branch'], role=UserProfile.Role.ADMINISTRADOR,
        )
        self.authorization = request_supervisor_authorization(
            requesting_user=self.tenant['user'], email=self.admin.email, password='testpass123',
        )

    def test_consume_marks_token_as_used(self):
        consume_supervisor_authorization(token=self.authorization.token, consuming_user=self.tenant['user'])
        self.authorization.refresh_from_db()
        self.assertTrue(self.authorization.is_used)

    def test_cannot_consume_the_same_token_twice(self):
        consume_supervisor_authorization(token=self.authorization.token, consuming_user=self.tenant['user'])
        with self.assertRaises(AuthorizationError):
            consume_supervisor_authorization(token=self.authorization.token, consuming_user=self.tenant['user'])

    def test_cannot_consume_an_expired_token(self):
        self.authorization.expires_at = timezone.now() - timedelta(seconds=1)
        self.authorization.save(update_fields=['expires_at'])
        with self.assertRaises(AuthorizationError):
            consume_supervisor_authorization(token=self.authorization.token, consuming_user=self.tenant['user'])
        self.authorization.refresh_from_db()
        self.assertFalse(self.authorization.is_used)

    def test_cannot_consume_an_invalid_token(self):
        with self.assertRaises(AuthorizationError):
            consume_supervisor_authorization(token='no-existe-este-token', consuming_user=self.tenant['user'])

    def test_cannot_consume_a_token_requested_by_another_user(self):
        other_cajero, _ = create_user_with_profile(
            'otro@donchuy.test', self.tenant['branch'], capabilities={'handles_cash': True},
        )
        with self.assertRaises(AuthorizationError):
            consume_supervisor_authorization(token=self.authorization.token, consuming_user=other_cajero)
        self.authorization.refresh_from_db()
        self.assertFalse(self.authorization.is_used)


class RequestSupervisorAuthorizationApiTests(APITestCase):
    def setUp(self):
        self.tenant = create_full_tenant('Abarrotes Don Chuy', 'Centro', 'cajero@donchuy.test')
        self.admin, _ = create_user_with_profile(
            'admin@donchuy.test', self.tenant['branch'], role=UserProfile.Role.ADMINISTRADOR,
        )

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def test_successful_request_returns_token(self):
        self._auth(self.tenant['user'])
        response = self.client.post(
            '/api/v1/auth/authorize-exception/',
            {'email': self.admin.email, 'password': 'testpass123', 'reason': 'cancelación de venta'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('token', response.data)
        self.assertEqual(response.data['supervisor_email'], self.admin.email)

    def test_wrong_password_returns_403(self):
        self._auth(self.tenant['user'])
        response = self.client.post(
            '/api/v1/auth/authorize-exception/',
            {'email': self.admin.email, 'password': 'wrong'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_supervisor_without_authority_returns_403(self):
        other_cajero, _ = create_user_with_profile('otro@donchuy.test', self.tenant['branch'])
        self._auth(self.tenant['user'])
        response = self.client.post(
            '/api/v1/auth/authorize-exception/',
            {'email': other_cajero.email, 'password': 'testpass123'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_cross_tenant_supervisor_returns_403(self):
        other_tenant = create_full_tenant(
            'Papelería La Estrella', 'Norte', 'admin@estrella.test', role=UserProfile.Role.ADMINISTRADOR,
        )
        self._auth(self.tenant['user'])
        response = self.client.post(
            '/api/v1/auth/authorize-exception/',
            {'email': other_tenant['user'].email, 'password': 'testpass123'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(SupervisorAuthorization.objects.count(), 0)

    def test_unauthenticated_caller_is_rejected(self):
        response = self.client.post(
            '/api/v1/auth/authorize-exception/',
            {'email': self.admin.email, 'password': 'testpass123'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_requesting_cajero_own_jwt_session_keeps_working_after_request(self):
        # El punto central del mecanismo: pedir la autorización NO cierra
        # ni toca la sesión del cajero que la solicita.
        self._auth(self.tenant['user'])
        self.client.post(
            '/api/v1/auth/authorize-exception/',
            {'email': self.admin.email, 'password': 'testpass123'},
            format='json',
        )
        response = self.client.get('/api/v1/branches/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
