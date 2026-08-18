"""Tests de aislamiento multi-tenant.

Esta es la pieza de mayor riesgo de seguridad del sistema (ver CLAUDE.md #2 y
arquitectura_tecnica_pos.md sección 5/8): un tenant nunca debe poder ver ni
tocar datos de otro, sin importar si se consulta el manager directo o la API.
No basta con probar el happy path de un solo tenant — cada test aquí arma
DOS tenants y confirma la frontera entre ambos explícitamente.
"""
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from tenants.models import Branch, CompanySettings, UserProfile
from tenants.tests.factories import create_full_tenant


class TenantScopedManagerIsolationTests(TestCase):
    """Nivel manager/queryset — sin pasar por la API."""

    def setUp(self):
        self.tenant_a = create_full_tenant('Abarrotes Don Chuy', 'Centro', 'admin@donchuy.test')
        self.tenant_b = create_full_tenant('Papelería La Estrella', 'Norte', 'admin@estrella.test')

    def test_for_user_only_returns_own_branches(self):
        visible = Branch.objects.for_user(self.tenant_a['user'])
        self.assertEqual(list(visible), [self.tenant_a['branch']])
        self.assertNotIn(self.tenant_b['branch'], visible)

    def test_for_user_only_returns_own_company_settings(self):
        visible = CompanySettings.objects.for_user(self.tenant_a['user'])
        self.assertEqual(list(visible), [self.tenant_a['settings']])
        self.assertNotIn(self.tenant_b['settings'], visible)

    def test_for_user_only_returns_own_user_profiles(self):
        visible = UserProfile.objects.for_user(self.tenant_a['user'])
        self.assertEqual(list(visible), [self.tenant_a['profile']])
        self.assertNotIn(self.tenant_b['profile'], visible)

    def test_for_company_filters_explicitly(self):
        self.assertEqual(
            list(Branch.objects.for_company(self.tenant_a['company'])),
            [self.tenant_a['branch']],
        )
        self.assertEqual(
            list(Branch.objects.for_company(self.tenant_b['company'])),
            [self.tenant_b['branch']],
        )

    def test_for_company_with_none_returns_nothing(self):
        # Un usuario sin profile (sin company resuelta) no debe ver "todo"
        # por accidente si algo llama for_company(None) — debe ver nada.
        self.assertEqual(list(Branch.objects.for_company(None)), [])

    def test_unscoped_manager_still_sees_everything(self):
        # Confirma que el aislamiento vive en for_user/for_company, no en
        # que el modelo "pierda" filas — para diferenciar "no hay datos" de
        # "los datos existen pero están bien aislados".
        self.assertEqual(Branch.objects.count(), 2)


class BranchApiIsolationTests(APITestCase):
    """Nivel API — el mismo aislamiento pero a través de un ViewSet real
    (TenantScopedViewSetMixin), que es como el frontend realmente consulta
    los datos."""

    def setUp(self):
        self.tenant_a = create_full_tenant('Abarrotes Don Chuy', 'Centro', 'admin@donchuy.test')
        self.tenant_b = create_full_tenant('Papelería La Estrella', 'Norte', 'admin@estrella.test')

    def _auth_as(self, user):
        self.client.force_authenticate(user=user)

    def test_list_only_returns_own_branches(self):
        self._auth_as(self.tenant_a['user'])
        response = self.client.get('/api/v1/branches/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [row['id'] for row in response.data['results']]
        self.assertEqual(ids, [self.tenant_a['branch'].id])

    def test_cannot_retrieve_other_tenant_branch_by_id(self):
        self._auth_as(self.tenant_a['user'])
        response = self.client.get(f"/api/v1/branches/{self.tenant_b['branch'].id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_cannot_update_other_tenant_branch_by_id(self):
        self._auth_as(self.tenant_a['user'])
        response = self.client.patch(
            f"/api/v1/branches/{self.tenant_b['branch'].id}/",
            {'name': 'hackeado'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.tenant_b['branch'].refresh_from_db()
        self.assertNotEqual(self.tenant_b['branch'].name, 'hackeado')

    def test_created_branch_is_stamped_with_caller_company_not_client_supplied(self):
        self._auth_as(self.tenant_a['user'])
        # Aunque el cliente mandara un company_id ajeno, perform_create lo
        # ignora y siempre usa la company del usuario autenticado.
        response = self.client.post(
            '/api/v1/branches/',
            {'name': 'Sucursal Nueva', 'address': '', 'company': self.tenant_b['company'].id},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = Branch.objects.get(id=response.data['id'])
        self.assertEqual(created.company_id, self.tenant_a['company'].id)

    def test_unauthenticated_request_is_rejected(self):
        response = self.client.get('/api/v1/branches/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
