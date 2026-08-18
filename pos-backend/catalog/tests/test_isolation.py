"""Aislamiento multi-tenant para catalog — mismo estándar que tenants/sales:
manager directo, API real, y el vector de IDOR vía FK cruzado (un tenant
pasando el id de una category/supplier/product ajena)."""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from catalog.models import Batch, Category, Product
from catalog.tests.factories import create_batch, create_category, create_product, create_supplier
from tenants.models import UserProfile
from tenants.tests.factories import create_full_tenant, create_user_with_profile


class CatalogManagerIsolationTests(TestCase):
    def setUp(self):
        self.tenant_a = create_full_tenant('Abarrotes Don Chuy', 'Centro', 'admin@donchuy.test')
        self.tenant_b = create_full_tenant('Papelería La Estrella', 'Norte', 'admin@estrella.test')
        self.category_a = create_category(self.tenant_a['company'])
        self.category_b = create_category(self.tenant_b['company'])
        self.product_a = create_product(self.tenant_a['company'], category=self.category_a)
        self.product_b = create_product(self.tenant_b['company'], category=self.category_b)
        self.batch_a = create_batch(self.product_a, self.tenant_a['branch'])
        self.batch_b = create_batch(self.product_b, self.tenant_b['branch'])

    def test_for_user_only_returns_own_categories(self):
        visible = Category.objects.for_user(self.tenant_a['user'])
        self.assertEqual(list(visible), [self.category_a])

    def test_for_user_only_returns_own_products(self):
        visible = Product.objects.for_user(self.tenant_a['user'])
        self.assertEqual(list(visible), [self.product_a])

    def test_for_user_only_returns_own_batches(self):
        visible = Batch.objects.for_user(self.tenant_a['user'])
        self.assertEqual(list(visible), [self.batch_a])

    def test_unscoped_manager_sees_both_tenants(self):
        self.assertEqual(Product.objects.count(), 2)
        self.assertEqual(Batch.objects.count(), 2)


class CatalogApiIsolationTests(APITestCase):
    def setUp(self):
        self.tenant_a = create_full_tenant(
            'Abarrotes Don Chuy', 'Centro', 'admin@donchuy.test', role=UserProfile.Role.ADMINISTRADOR,
        )
        self.tenant_b = create_full_tenant(
            'Papelería La Estrella', 'Norte', 'admin@estrella.test', role=UserProfile.Role.ADMINISTRADOR,
        )
        self.category_a = create_category(self.tenant_a['company'])
        self.category_b = create_category(self.tenant_b['company'])
        self.supplier_a = create_supplier(self.tenant_a['company'])
        self.product_a = create_product(self.tenant_a['company'], category=self.category_a)
        self.product_b = create_product(self.tenant_b['company'], category=self.category_b)

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def test_list_products_only_returns_own_tenant(self):
        self._auth(self.tenant_a['user'])
        response = self.client.get('/api/v1/products/')
        ids = [row['id'] for row in response.data['results']]
        self.assertEqual(ids, [self.product_a.id])

    def test_cannot_retrieve_other_tenant_product(self):
        self._auth(self.tenant_a['user'])
        response = self.client.get(f'/api/v1/products/{self.product_b.id}/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_cannot_create_product_pointing_to_other_tenant_category(self):
        self._auth(self.tenant_a['user'])
        response = self.client.post(
            '/api/v1/products/',
            {
                'name': 'Producto colado', 'sku': 'HACK-1',
                'category': self.category_b.id,
                'cost_price': '1.00', 'sale_price': '2.00',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Product.objects.filter(sku='HACK-1').exists())

    def test_create_product_with_own_tenant_category_and_supplier_succeeds(self):
        self._auth(self.tenant_a['user'])
        response = self.client.post(
            '/api/v1/products/',
            {
                'name': 'Refresco 600ml', 'sku': 'REF-600',
                'category': self.category_a.id, 'supplier': self.supplier_a.id,
                'cost_price': '10.00', 'sale_price': '15.00',
                'unit_type': 'PIEZA',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['company'], self.tenant_a['company'].id)

    def test_plain_cajero_can_read_products_but_not_create_one(self):
        # Punto 5/8: catálogo (producto, precio, relacionados) es exclusivo
        # de ADMINISTRADOR — un CAJERO sigue pudiendo leer (el buscador de
        # venta lo necesita) pero no crear/editar.
        cajero, _ = create_user_with_profile(
            'cajero@donchuy.test', self.tenant_a['branch'], capabilities={'handles_cash': True},
        )
        self._auth(cajero)

        get_response = self.client.get('/api/v1/products/')
        self.assertEqual(get_response.status_code, status.HTTP_200_OK)

        post_response = self.client.post(
            '/api/v1/products/',
            {'name': 'Intento no autorizado', 'sku': 'NO-AUTH', 'category': self.category_a.id, 'cost_price': '1.00', 'sale_price': '2.00'},
            format='json',
        )
        self.assertEqual(post_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Product.objects.filter(sku='NO-AUTH').exists())

    def test_cannot_create_batch_pointing_to_other_tenant_product(self):
        self._auth(self.tenant_a['user'])
        response = self.client.post(
            '/api/v1/batches/',
            {
                'product': self.product_b.id,
                'branch': self.tenant_a['branch'].id,
                'batch_number': 'HACK-L1',
                'initial_quantity': 10,
                'expiration_date': '2030-01-01',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Batch.objects.filter(batch_number='HACK-L1').exists())

    def test_unauthenticated_request_is_rejected(self):
        response = self.client.get('/api/v1/products/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class ProductSearchApiTests(APITestCase):
    def setUp(self):
        self.tenant_a = create_full_tenant('Abarrotes Don Chuy', 'Centro', 'admin@donchuy.test')
        self.tenant_b = create_full_tenant('Papelería La Estrella', 'Norte', 'admin@estrella.test')
        self.category_a = create_category(self.tenant_a['company'])
        self.leche = create_product(
            self.tenant_a['company'], category=self.category_a, name='Leche entera 1L', sku='LEC-1L',
        )
        self.refresco = create_product(
            self.tenant_a['company'], category=self.category_a, name='Refresco 600ml', sku='REF-600',
            barcode='7501234567890',
        )

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def test_search_by_name(self):
        self._auth(self.tenant_a['user'])
        response = self.client.get('/api/v1/products/?search=leche')
        ids = [row['id'] for row in response.data['results']]
        self.assertEqual(ids, [self.leche.id])

    def test_search_by_sku(self):
        self._auth(self.tenant_a['user'])
        response = self.client.get('/api/v1/products/?search=REF-600')
        ids = [row['id'] for row in response.data['results']]
        self.assertEqual(ids, [self.refresco.id])

    def test_search_by_barcode(self):
        self._auth(self.tenant_a['user'])
        response = self.client.get('/api/v1/products/?search=7501234567890')
        ids = [row['id'] for row in response.data['results']]
        self.assertEqual(ids, [self.refresco.id])

    def test_search_never_returns_another_tenants_product(self):
        create_product(self.tenant_b['company'], name='Leche entera 1L', sku='LEC-1L-B')
        self._auth(self.tenant_a['user'])
        response = self.client.get('/api/v1/products/?search=leche')
        ids = [row['id'] for row in response.data['results']]
        self.assertEqual(ids, [self.leche.id])


class RelatedProductsApiTests(APITestCase):
    def setUp(self):
        self.tenant_a = create_full_tenant(
            'Abarrotes Don Chuy', 'Centro', 'admin@donchuy.test', role=UserProfile.Role.ADMINISTRADOR,
        )
        self.tenant_b = create_full_tenant(
            'Papelería La Estrella', 'Norte', 'admin@estrella.test', role=UserProfile.Role.ADMINISTRADOR,
        )
        self.pan = create_product(self.tenant_a['company'], name='Pan de caja', sku='PAN-API')
        self.mantequilla = create_product(self.tenant_a['company'], name='Mantequilla', sku='MANT-API')
        self.producto_ajeno = create_product(self.tenant_b['company'], name='Ajeno', sku='AJENO-API')

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def test_admin_can_set_related_products_via_patch(self):
        self._auth(self.tenant_a['user'])
        response = self.client.patch(
            f'/api/v1/products/{self.pan.id}/', {'related_products': [self.mantequilla.id]}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([p['id'] for p in response.data['related_products_detail']], [self.mantequilla.id])

        # Simétrico: se ve también del otro lado sin tocarlo directo.
        self.mantequilla.refresh_from_db()
        self.assertIn(self.pan, self.mantequilla.related_products.all())

    def test_cannot_relate_a_product_from_another_tenant(self):
        self._auth(self.tenant_a['user'])
        response = self.client.patch(
            f'/api/v1/products/{self.pan.id}/', {'related_products': [self.producto_ajeno.id]}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(list(self.pan.related_products.all()), [])

    def test_cannot_relate_a_product_to_itself(self):
        self._auth(self.tenant_a['user'])
        response = self.client.patch(
            f'/api/v1/products/{self.pan.id}/', {'related_products': [self.pan.id]}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_plain_cajero_cannot_set_related_products(self):
        cajero, _ = create_user_with_profile(
            'cajero@donchuy.test', self.tenant_a['branch'], capabilities={'handles_cash': True},
        )
        self._auth(cajero)
        response = self.client.patch(
            f'/api/v1/products/{self.pan.id}/', {'related_products': [self.mantequilla.id]}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class CatalogInventoryPermissionBoundaryTests(APITestCase):
    """Punto 8: CRUD de catálogo/inventario dividido en dos niveles —
    producto/precio/catálogo (Category, Supplier, Product) exclusivo de
    ADMINISTRADOR para escribir (cualquiera lee, ver
    test_plain_cajero_can_read_products_but_not_create_one arriba para el
    caso de Product); lotes/ajustes de stock (Batch) para
    ADMINISTRADOR o Supervisor, ni siquiera lectura para un cajero plano
    (a diferencia de Product, ningún flujo de venta necesita leer Batch
    directo por API)."""

    def setUp(self):
        self.tenant = create_full_tenant(
            'Abarrotes Don Chuy', 'Centro', 'admin@donchuy.test', role=UserProfile.Role.ADMINISTRADOR,
        )
        self.category = create_category(self.tenant['company'])
        self.supplier = create_supplier(self.tenant['company'])
        self.product = create_product(self.tenant['company'], category=self.category)
        self.batch = create_batch(self.product, self.tenant['branch'])

        self.cajero, _ = create_user_with_profile(
            'cajero@donchuy.test', self.tenant['branch'], capabilities={'handles_cash': True},
        )
        self.supervisor, _ = create_user_with_profile(
            'supervisor@donchuy.test', self.tenant['branch'], capabilities={'can_authorize_exceptions': True},
        )

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def test_administrador_can_create_category(self):
        self._auth(self.tenant['user'])
        response = self.client.post('/api/v1/categories/', {'name': 'Lácteos'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_plain_cajero_can_read_categories_but_not_create_one(self):
        self._auth(self.cajero)
        get_response = self.client.get('/api/v1/categories/')
        self.assertEqual(get_response.status_code, status.HTTP_200_OK)

        post_response = self.client.post('/api/v1/categories/', {'name': 'Intento no autorizado'}, format='json')
        self.assertEqual(post_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_supervisor_cannot_create_category(self):
        # Categoría/proveedor son catálogo, no inventario — el gate es
        # ADMINISTRADOR estricto, un Supervisor NO pasa aquí (a
        # diferencia de Batch, ver tests de abajo).
        self._auth(self.supervisor)
        response = self.client.post('/api/v1/categories/', {'name': 'Intento supervisor'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_plain_cajero_can_read_suppliers_but_not_create_one(self):
        self._auth(self.cajero)
        get_response = self.client.get('/api/v1/suppliers/')
        self.assertEqual(get_response.status_code, status.HTTP_200_OK)

        post_response = self.client.post('/api/v1/suppliers/', {'name': 'Intento no autorizado'}, format='json')
        self.assertEqual(post_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_administrador_can_create_batch(self):
        self._auth(self.tenant['user'])
        response = self.client.post(
            '/api/v1/batches/',
            {
                'product': self.product.id, 'branch': self.tenant['branch'].id,
                'batch_number': 'ADMIN-L1', 'initial_quantity': 10, 'expiration_date': '2030-01-01',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_supervisor_can_create_batch(self):
        self._auth(self.supervisor)
        response = self.client.post(
            '/api/v1/batches/',
            {
                'product': self.product.id, 'branch': self.tenant['branch'].id,
                'batch_number': 'SUP-L1', 'initial_quantity': 10, 'expiration_date': '2030-01-01',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_plain_cajero_cannot_read_or_create_batches(self):
        self._auth(self.cajero)
        get_response = self.client.get('/api/v1/batches/')
        self.assertEqual(get_response.status_code, status.HTTP_403_FORBIDDEN)

        post_response = self.client.post(
            '/api/v1/batches/',
            {
                'product': self.product.id, 'branch': self.tenant['branch'].id,
                'batch_number': 'CAJERO-L1', 'initial_quantity': 10, 'expiration_date': '2030-01-01',
            },
            format='json',
        )
        self.assertEqual(post_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Batch.objects.filter(batch_number='CAJERO-L1').exists())


class ProductNearestBatchExpirationTests(APITestCase):
    """Punto 4: el aviso de caducidad próxima en el buscador de venta viene
    de este campo — se prueba aquí, en el mismo endpoint que ProductSearch
    usa de verdad, no en un endpoint aparte."""

    def setUp(self):
        self.tenant = create_full_tenant('Abarrotes Don Chuy', 'Centro', 'admin@donchuy.test')
        self.product = create_product(self.tenant['company'], name='Yogurt', sku='YOG-1')
        self.today = timezone.localdate()

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def test_reports_the_soonest_expiring_batch_with_stock(self):
        create_batch(self.product, self.tenant['branch'], batch_number='LEJANO', initial_quantity=5, expiration_date=self.today + timedelta(days=20))
        create_batch(self.product, self.tenant['branch'], batch_number='CERCANO', initial_quantity=5, expiration_date=self.today + timedelta(days=3))

        self._auth(self.tenant['user'])
        response = self.client.get(f'/api/v1/products/{self.product.id}/')
        self.assertEqual(response.data['nearest_batch_expiration'], self.today + timedelta(days=3))

    def test_ignores_expired_and_sold_out_batches(self):
        create_batch(self.product, self.tenant['branch'], batch_number='VENCIDO', initial_quantity=5, expiration_date=self.today - timedelta(days=1))
        sold_out = create_batch(self.product, self.tenant['branch'], batch_number='AGOTADO', initial_quantity=5, expiration_date=self.today + timedelta(days=2))
        sold_out.current_quantity = 0
        sold_out.save(update_fields=['current_quantity'])

        self._auth(self.tenant['user'])
        response = self.client.get(f'/api/v1/products/{self.product.id}/')
        self.assertIsNone(response.data['nearest_batch_expiration'])

    def test_null_when_product_has_no_batches(self):
        self._auth(self.tenant['user'])
        response = self.client.get(f'/api/v1/products/{self.product.id}/')
        self.assertIsNone(response.data['nearest_batch_expiration'])
