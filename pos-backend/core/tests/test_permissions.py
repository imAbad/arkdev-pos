"""Tests del gate de permisos por capability.

Unit-level: se ejercita has_permission() directo con un request/view falsos,
sin necesidad de un endpoint real — el endpoint real que consume esto
(apertura/cierre de turno, gateado por HandlesCash) se prueba end-to-end en
sales/tests/test_cash_shift.py.
"""
from django.test import TestCase

from core.permissions import CanAuthorizeExceptions, HandlesCash, HasCapability, capability_required
from tenants.tests.factories import create_branch, create_company, create_user_with_profile
from tenants.models import User


class FakeRequest:
    def __init__(self, user):
        self.user = user


class FakeView:
    required_capability = None


class CapabilityRequiredFactoryTests(TestCase):
    def test_generates_distinct_permission_classes_per_capability(self):
        cls_a = capability_required('can_authorize_exceptions')
        cls_b = capability_required('handles_cash')
        self.assertNotEqual(cls_a, cls_b)
        self.assertTrue(issubclass(cls_a, HasCapability))
        self.assertEqual(cls_a.capability, 'can_authorize_exceptions')
        self.assertEqual(cls_b.capability, 'handles_cash')

    def test_prebuilt_shortcuts_match_expected_capability(self):
        self.assertEqual(CanAuthorizeExceptions.capability, 'can_authorize_exceptions')
        self.assertEqual(HandlesCash.capability, 'handles_cash')


class HasCapabilityPermissionTests(TestCase):
    def setUp(self):
        self.company = create_company('Abarrotes Don Chuy')
        self.branch = create_branch(self.company)

    def _user_with_capabilities(self, email, capabilities):
        user, _ = create_user_with_profile(email, self.branch, capabilities=capabilities)
        return user

    def test_allows_user_whose_profile_has_capability_true(self):
        user = self._user_with_capabilities('super@donchuy.test', {'can_authorize_exceptions': True})
        permission = CanAuthorizeExceptions()
        self.assertTrue(permission.has_permission(FakeRequest(user), FakeView()))

    def test_denies_user_whose_profile_has_capability_false(self):
        user = self._user_with_capabilities('cajero@donchuy.test', {'can_authorize_exceptions': False})
        permission = CanAuthorizeExceptions()
        self.assertFalse(permission.has_permission(FakeRequest(user), FakeView()))

    def test_denies_user_whose_profile_lacks_the_key_entirely(self):
        user = self._user_with_capabilities('cajero@donchuy.test', {})
        permission = CanAuthorizeExceptions()
        self.assertFalse(permission.has_permission(FakeRequest(user), FakeView()))

    def test_denies_user_without_profile_even_if_staff(self):
        staff = User.objects.create_user(email='staff@arkdev.test', password='x', is_staff=True)
        permission = CanAuthorizeExceptions()
        self.assertFalse(permission.has_permission(FakeRequest(staff), FakeView()))

    def test_two_capabilities_are_independent(self):
        # handles_cash=True no implica can_authorize_exceptions=True.
        user = self._user_with_capabilities('cajero@donchuy.test', {'handles_cash': True})
        self.assertTrue(HandlesCash().has_permission(FakeRequest(user), FakeView()))
        self.assertFalse(CanAuthorizeExceptions().has_permission(FakeRequest(user), FakeView()))

    def test_view_level_required_capability_overrides_instance_default(self):
        user = self._user_with_capabilities('cajero@donchuy.test', {'handles_cash': True})
        view = FakeView()
        view.required_capability = 'handles_cash'
        # Se instancia como CanAuthorizeExceptions pero el view pide otra cosa.
        permission = CanAuthorizeExceptions()
        self.assertTrue(permission.has_permission(FakeRequest(user), view))

    def test_no_capability_configured_allows_by_default(self):
        user = self._user_with_capabilities('cajero@donchuy.test', {})
        self.assertTrue(HasCapability().has_permission(FakeRequest(user), FakeView()))
