"""core no define modelos concretos propios (BaseTenantModel es abstracto),
así que estos tests ejercitan el manager genérico a través de dos modelos
concretos distintos (tenants.Branch y tenants.CompanySettings) para probar
que el comportamiento de aislamiento es del manager/queryset compartido, no
de algo particular a un solo modelo."""
from django.test import TestCase

from tenants.models import Branch, CompanySettings
from tenants.tests.factories import create_full_tenant


class TenantScopedManagerGenericBehaviorTests(TestCase):
    def setUp(self):
        self.tenant_a = create_full_tenant('Tenant A', 'Sucursal A', 'a@a.test')
        self.tenant_b = create_full_tenant('Tenant B', 'Sucursal B', 'b@b.test')

    def test_for_company_is_consistent_across_models(self):
        for model, expected in (
            (Branch, self.tenant_a['branch']),
            (CompanySettings, self.tenant_a['settings']),
        ):
            with self.subTest(model=model):
                self.assertEqual(
                    list(model.objects.for_company(self.tenant_a['company'])),
                    [expected],
                )

    def test_for_user_delegates_to_for_company_via_profile(self):
        # for_user no debe requerir código específico por modelo: solo
        # necesita que el modelo tenga `company` y el manager herede de
        # TenantScopedManager.
        self.assertEqual(
            list(Branch.objects.for_user(self.tenant_a['user'])),
            list(Branch.objects.for_company(self.tenant_a['company'])),
        )

    def test_user_without_profile_sees_nothing(self):
        from tenants.models import User

        orphan = User.objects.create_user(email='sin-profile@test.com', password='x')
        self.assertEqual(list(Branch.objects.for_user(orphan)), [])
