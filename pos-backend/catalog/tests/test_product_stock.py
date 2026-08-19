"""Observación de sesión (ronda de 4 piezas, punto 1): la tabla principal
de Inventario no mostraba stock, solo se veía abriendo "Lotes" producto
por producto. `ProductSerializer.current_stock` es el total sumado de
lotes vigentes (no vencidos, con existencia > 0) — None (no 0) cuando el
producto no usa `requires_batch`, porque ese caso no tiene NINGÚN
mecanismo de conteo de existencias en el modelo actual (mismo hallazgo
que ya limita catalog.services.low_stock_products)."""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory, APITestCase

from catalog.tests.factories import create_batch, create_product
from tenants.models import UserProfile
from tenants.tests.factories import create_branch, create_full_tenant


class CurrentStockSerializerTests(TestCase):
    def setUp(self):
        self.tenant = create_full_tenant('Abarrotes Don Chuy', 'Centro', 'admin@donchuy.test')
        self.company = self.tenant['company']
        self.branch = self.tenant['branch']

    def _serialize(self, product, branch_id=None):
        from catalog.serializers import ProductSerializer
        params = {'branch': branch_id} if branch_id is not None else {}
        django_request = APIRequestFactory().get('/api/v1/products/', params)
        request = Request(django_request)
        request.user = self.tenant['user']
        return ProductSerializer(product, context={'request': request}).data

    def test_none_for_a_product_that_does_not_require_batch(self):
        product = create_product(self.company, sku='NOBATCH-1', requires_batch=False)
        create_batch(product, self.branch, initial_quantity=10)  # aunque tenga lotes, no se rastrea por este camino

        data = self._serialize(product)
        self.assertIsNone(data['current_stock'])

    def test_sums_current_quantity_across_batches(self):
        product = create_product(self.company, sku='BATCH-1', requires_batch=True)
        create_batch(product, self.branch, batch_number='L-1', initial_quantity=10)
        create_batch(product, self.branch, batch_number='L-2', initial_quantity=5)

        data = self._serialize(product)
        self.assertEqual(data['current_stock'], 15)

    def test_zero_when_no_batches_exist_yet(self):
        product = create_product(self.company, sku='BATCH-EMPTY', requires_batch=True)
        data = self._serialize(product)
        self.assertEqual(data['current_stock'], 0)

    def test_excludes_expired_batches(self):
        product = create_product(self.company, sku='BATCH-EXP', requires_batch=True)
        create_batch(product, self.branch, batch_number='VIGENTE', initial_quantity=8)
        create_batch(
            product, self.branch, batch_number='VENCIDO', initial_quantity=100,
            expiration_date=timezone.localdate() - timedelta(days=1),
        )

        data = self._serialize(product)
        self.assertEqual(data['current_stock'], 8)

    def test_excludes_batches_with_no_remaining_stock(self):
        product = create_product(self.company, sku='BATCH-SOLDOUT', requires_batch=True)
        batch = create_batch(product, self.branch, batch_number='AGOTADO', initial_quantity=5)
        batch.current_quantity = 0
        batch.save(update_fields=['current_quantity'])
        create_batch(product, self.branch, batch_number='CON-STOCK', initial_quantity=3)

        data = self._serialize(product)
        self.assertEqual(data['current_stock'], 3)

    def test_scoped_to_a_branch_when_one_is_given(self):
        other_branch = create_branch(self.company, name='Sucursal Norte')
        product = create_product(self.company, sku='MULTI-BRANCH', requires_batch=True)
        create_batch(product, self.branch, batch_number='CENTRO', initial_quantity=10)
        create_batch(product, other_branch, batch_number='NORTE', initial_quantity=4)

        self.assertEqual(self._serialize(product)['current_stock'], 14)
        self.assertEqual(self._serialize(product, branch_id=self.branch.id)['current_stock'], 10)
        self.assertEqual(self._serialize(product, branch_id=other_branch.id)['current_stock'], 4)


class CurrentStockApiTests(APITestCase):
    def setUp(self):
        self.tenant = create_full_tenant(
            'Abarrotes Don Chuy', 'Centro', 'admin@donchuy.test', role=UserProfile.Role.ADMINISTRADOR,
        )
        self.company = self.tenant['company']
        self.branch = self.tenant['branch']

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def test_current_stock_visible_over_the_products_endpoint(self):
        product = create_product(self.company, sku='API-BATCH', requires_batch=True)
        create_batch(product, self.branch, initial_quantity=7)
        self._auth(self.tenant['user'])

        response = self.client.get('/api/v1/products/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        row = next(r for r in response.data['results'] if r['id'] == product.id)
        self.assertEqual(row['current_stock'], 7)

    def test_current_stock_filtered_by_branch_query_param(self):
        other_branch = create_branch(self.company, name='Sucursal Norte')
        product = create_product(self.company, sku='API-MULTI', requires_batch=True)
        create_batch(product, self.branch, batch_number='CENTRO', initial_quantity=6)
        create_batch(product, other_branch, batch_number='NORTE', initial_quantity=9)
        self._auth(self.tenant['user'])

        response = self.client.get('/api/v1/products/', {'branch': self.branch.id})

        row = next(r for r in response.data['results'] if r['id'] == product.id)
        self.assertEqual(row['current_stock'], 6)
