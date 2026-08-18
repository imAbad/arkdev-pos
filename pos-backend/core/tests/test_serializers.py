"""TenantScopedFieldsMixin — probado genérico, no atado a un solo serializer
real (el caso real de uso, CashRegisterSerializer.branch, se prueba
end-to-end en sales/tests/test_cash_shift.py)."""
from django.test import TestCase
from rest_framework import serializers
from rest_framework.test import APIRequestFactory

from core.serializers import TenantScopedFieldsMixin
from tenants.models import UserProfile
from tenants.tests.factories import create_full_tenant


class _ProfileByBranchSerializer(TenantScopedFieldsMixin, serializers.ModelSerializer):
    tenant_scoped_fields = ('branch',)

    class Meta:
        model = UserProfile
        fields = ['id', 'branch', 'role']


class TenantScopedFieldsMixinTests(TestCase):
    def setUp(self):
        self.tenant_a = create_full_tenant('Tenant A', 'Sucursal A', 'a@a.test')
        self.tenant_b = create_full_tenant('Tenant B', 'Sucursal B', 'b@b.test')
        self.factory = APIRequestFactory()

    def _serializer_for(self, user):
        request = self.factory.post('/')
        request.user = user
        return _ProfileByBranchSerializer(context={'request': request})

    def test_field_queryset_is_scoped_to_requesting_user_tenant(self):
        serializer = self._serializer_for(self.tenant_a['user'])
        self.assertEqual(
            list(serializer.fields['branch'].queryset),
            [self.tenant_a['branch']],
        )
        self.assertNotIn(self.tenant_b['branch'], serializer.fields['branch'].queryset)

    def test_different_users_get_different_scoped_querysets(self):
        serializer_a = self._serializer_for(self.tenant_a['user'])
        serializer_b = self._serializer_for(self.tenant_b['user'])
        self.assertEqual(list(serializer_a.fields['branch'].queryset), [self.tenant_a['branch']])
        self.assertEqual(list(serializer_b.fields['branch'].queryset), [self.tenant_b['branch']])

    def test_without_request_in_context_field_keeps_default_unscoped_queryset(self):
        # Documented, no un hueco de seguridad: toda vista real de DRF pasa
        # `request` en el contexto vía get_serializer(); esto solo cubre el
        # caso de instanciar el serializer a mano sin contexto (ej. en un
        # test o script), donde no hay usuario del que derivar el scope.
        serializer = _ProfileByBranchSerializer()
        self.assertGreaterEqual(serializer.fields['branch'].queryset.count(), 2)
