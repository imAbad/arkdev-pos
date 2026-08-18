"""Aislamiento multi-tenant y permisos negados para Sale — mismo estándar
que el resto del proyecto (manager directo, API real, y el vector de IDOR
vía FK cruzado, aquí con product_id/batch_id/cash_shift)."""
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from catalog.tests.factories import create_batch
from sales.models import Sale
from sales.tests.factories import create_checkout_context, make_sale
from tenants.tests.factories import create_user_with_profile


class SaleManagerIsolationTests(TestCase):
    def setUp(self):
        self.ctx_a = create_checkout_context('Abarrotes Don Chuy', 'Centro', 'a@donchuy.test')
        self.ctx_b = create_checkout_context('Papelería La Estrella', 'Norte', 'b@estrella.test')
        self.sale_a = make_sale(self.ctx_a['shift'], self.ctx_a['product'])
        self.sale_b = make_sale(self.ctx_b['shift'], self.ctx_b['product'])

    def test_for_user_only_returns_own_sales(self):
        visible = Sale.objects.for_user(self.ctx_a['user'])
        self.assertEqual(list(visible), [self.sale_a])

    def test_unscoped_manager_sees_both_tenants(self):
        self.assertEqual(Sale.objects.count(), 2)


class SaleApiTests(APITestCase):
    def setUp(self):
        self.ctx_a = create_checkout_context('Abarrotes Don Chuy', 'Centro', 'a@donchuy.test')
        self.ctx_b = create_checkout_context('Papelería La Estrella', 'Norte', 'b@estrella.test')

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def _checkout_payload(self, ctx, **overrides):
        payload = {
            'cash_shift': ctx['shift'].id,
            'details': [{'product_id': ctx['product'].id, 'quantity': '1.000', 'unit_price': '10.00'}],
            'payments': [{'method': 'CASH', 'amount': str(ctx['product'].tax_rate / 100 * 10 + 10)}],
        }
        payload.update(overrides)
        return payload

    def test_create_sale_happy_path(self):
        self._auth(self.ctx_a['user'])
        response = self.client.post('/api/v1/sales/create-sale/', self._checkout_payload(self.ctx_a), format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['status'], 'COMPLETED')
        self.assertEqual(len(response.data['details']), 1)
        self.assertEqual(len(response.data['payments']), 1)

    def test_list_sales_only_returns_own_tenant(self):
        sale_a = make_sale(self.ctx_a['shift'], self.ctx_a['product'])
        make_sale(self.ctx_b['shift'], self.ctx_b['product'])
        self._auth(self.ctx_a['user'])
        response = self.client.get('/api/v1/sales/')
        ids = [row['id'] for row in response.data['results']]
        self.assertEqual(ids, [sale_a.id])

    def test_cannot_retrieve_other_tenant_sale(self):
        sale_b = make_sale(self.ctx_b['shift'], self.ctx_b['product'])
        self._auth(self.ctx_a['user'])
        response = self.client.get(f'/api/v1/sales/{sale_b.id}/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_create_sale_rejects_cash_shift_from_other_tenant(self):
        self._auth(self.ctx_a['user'])
        payload = self._checkout_payload(self.ctx_a, cash_shift=self.ctx_b['shift'].id)
        response = self.client.post('/api/v1/sales/create-sale/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Sale.objects.count(), 0)

    def test_create_sale_rejects_product_from_other_tenant(self):
        self._auth(self.ctx_a['user'])
        payload = self._checkout_payload(self.ctx_a)
        payload['details'] = [{'product_id': self.ctx_b['product'].id, 'quantity': '1.000', 'unit_price': '10.00'}]
        response = self.client.post('/api/v1/sales/create-sale/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(Sale.objects.count(), 0)

    def test_create_sale_rejects_batch_from_other_tenant(self):
        own_batch_holder = self.ctx_a['product']
        foreign_batch = create_batch(self.ctx_b['product'], self.ctx_b['branch'])
        self._auth(self.ctx_a['user'])
        payload = self._checkout_payload(self.ctx_a)
        payload['details'] = [{
            'product_id': own_batch_holder.id, 'batch_id': foreign_batch.id,
            'quantity': '1.000', 'unit_price': '10.00',
        }]
        response = self.client.post('/api/v1/sales/create-sale/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(Sale.objects.count(), 0)

    def test_user_without_handles_cash_capability_is_denied(self):
        cajero, _ = create_user_with_profile(
            'sincaja@donchuy.test', self.ctx_a['branch'], capabilities={'handles_cash': False},
        )
        self._auth(cajero)
        response = self.client.get('/api/v1/sales/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_request_is_rejected(self):
        response = self.client.get('/api/v1/sales/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
