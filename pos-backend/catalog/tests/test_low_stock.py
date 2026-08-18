"""Punto 7: endpoint de stock bajo — mismo gate que abrir turno
(HandlesCash, no restringido a admin/supervisor) y mismo estándar de
aislamiento multi-tenant que el resto de catalog."""
from rest_framework import status
from rest_framework.test import APITestCase

from catalog.tests.factories import create_batch, create_product
from tenants.models import UserProfile
from tenants.tests.factories import create_full_tenant, create_user_with_profile


class LowStockViewApiTests(APITestCase):
    def setUp(self):
        self.tenant_a = create_full_tenant(
            'Abarrotes Don Chuy', 'Centro', 'admin@donchuy.test', role=UserProfile.Role.ADMINISTRADOR,
        )
        self.tenant_b = create_full_tenant(
            'Papelería La Estrella', 'Norte', 'admin@estrella.test', role=UserProfile.Role.ADMINISTRADOR,
        )

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def test_administrador_sees_low_stock_products(self):
        product = create_product(
            self.tenant_a['company'], name='Yogurt', sku='YOG-1', requires_batch=True, min_stock=10,
        )
        create_batch(product, self.tenant_a['branch'], initial_quantity=2)

        self._auth(self.tenant_a['user'])
        response = self.client.get('/api/v1/low-stock/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['product_id'], product.id)

    def test_cajero_with_handles_cash_can_see_it(self):
        cajero, _ = create_user_with_profile(
            'cajero@donchuy.test', self.tenant_a['branch'], capabilities={'handles_cash': True},
        )
        product = create_product(
            self.tenant_a['company'], name='Yogurt', sku='YOG-1', requires_batch=True, min_stock=10,
        )
        create_batch(product, self.tenant_a['branch'], initial_quantity=2)

        self._auth(cajero)
        response = self.client.get('/api/v1/low-stock/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_cajero_without_handles_cash_is_forbidden(self):
        cajero, _ = create_user_with_profile('cajero2@donchuy.test', self.tenant_a['branch'])

        self._auth(cajero)
        response = self.client.get('/api/v1/low-stock/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_tenant_isolation(self):
        product_a = create_product(
            self.tenant_a['company'], name='Yogurt', sku='YOG-1', requires_batch=True, min_stock=10,
        )
        create_batch(product_a, self.tenant_a['branch'], initial_quantity=1)
        product_b = create_product(
            self.tenant_b['company'], name='Resistol', sku='RES-1', requires_batch=True, min_stock=10,
        )
        create_batch(product_b, self.tenant_b['branch'], initial_quantity=1)

        self._auth(self.tenant_a['user'])
        response = self.client.get('/api/v1/low-stock/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['product_id'], product_a.id)
