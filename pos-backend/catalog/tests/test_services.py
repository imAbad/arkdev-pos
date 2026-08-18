import threading
from datetime import timedelta
from decimal import Decimal

from django.db import connection, transaction
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from catalog.services import InsufficientStockError, decrement_batch_stock, decrement_stock_fefo, low_stock_products
from catalog.tests.factories import create_batch, create_product
from tenants.tests.factories import create_branch, create_company


class DecrementBatchStockTests(TestCase):
    def setUp(self):
        self.company = create_company('Abarrotes Don Chuy')
        self.branch = create_branch(self.company)
        self.product = create_product(self.company)
        self.batch = create_batch(self.product, self.branch, initial_quantity=10)

    def test_decrements_available_stock(self):
        decrement_batch_stock(batch=self.batch, quantity=4)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.current_quantity, 6)

    def test_raises_when_insufficient_stock(self):
        with self.assertRaises(InsufficientStockError):
            decrement_batch_stock(batch=self.batch, quantity=11)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.current_quantity, 10)

    def test_exact_remaining_stock_can_be_taken_down_to_zero(self):
        decrement_batch_stock(batch=self.batch, quantity=10)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.current_quantity, 0)


class DecrementStockFefoTests(TestCase):
    """Punto 1 de la sesión: verificación con evidencia de que
    decrement_batch_stock NO hacía FEFO (solo descontaba el lote exacto
    que se le pasara, sin ningún criterio de orden — confirmado leyendo
    el código antes de escribir estos tests). decrement_stock_fefo es la
    función nueva que sí lo hace real: al menos 3 lotes de fechas
    distintas, confirma que consume el de caducidad más próxima primero."""

    def setUp(self):
        self.company = create_company('Abarrotes Don Chuy')
        self.branch = create_branch(self.company)
        self.product = create_product(self.company, requires_batch=True)
        self.today = timezone.localdate()

    def test_consumes_the_soonest_expiring_batch_first_among_three(self):
        far = create_batch(self.product, self.branch, batch_number='LEJANO', initial_quantity=10, expiration_date=self.today + timedelta(days=90))
        near = create_batch(self.product, self.branch, batch_number='CERCANO', initial_quantity=10, expiration_date=self.today + timedelta(days=5))
        middle = create_batch(self.product, self.branch, batch_number='MEDIO', initial_quantity=10, expiration_date=self.today + timedelta(days=30))

        used = decrement_stock_fefo(product=self.product, branch=self.branch, quantity=4)

        self.assertEqual(used.id, near.id)
        near.refresh_from_db()
        far.refresh_from_db()
        middle.refresh_from_db()
        self.assertEqual(near.current_quantity, 6)
        self.assertEqual(far.current_quantity, 10)
        self.assertEqual(middle.current_quantity, 10)

    def test_skips_a_soon_expiring_batch_without_enough_stock_for_a_later_one(self):
        # El lote más próximo a caducar SÍ existe pero no alcanza para la
        # cantidad pedida — FEFO real no lo fuerza (no parte la línea
        # entre lotes), pasa al siguiente en orden que sí alcance.
        create_batch(self.product, self.branch, batch_number='CERCANO-POCO', initial_quantity=2, expiration_date=self.today + timedelta(days=5))
        enough = create_batch(self.product, self.branch, batch_number='MEDIO-SUFICIENTE', initial_quantity=10, expiration_date=self.today + timedelta(days=30))

        used = decrement_stock_fefo(product=self.product, branch=self.branch, quantity=5)
        self.assertEqual(used.id, enough.id)

    def test_ignores_already_expired_batches(self):
        create_batch(self.product, self.branch, batch_number='CADUCADO', initial_quantity=10, expiration_date=self.today - timedelta(days=1))
        valid = create_batch(self.product, self.branch, batch_number='VIGENTE', initial_quantity=10, expiration_date=self.today + timedelta(days=10))

        used = decrement_stock_fefo(product=self.product, branch=self.branch, quantity=3)
        self.assertEqual(used.id, valid.id)

    def test_raises_when_no_single_batch_covers_the_quantity(self):
        create_batch(self.product, self.branch, batch_number='A', initial_quantity=2, expiration_date=self.today + timedelta(days=5))
        create_batch(self.product, self.branch, batch_number='B', initial_quantity=2, expiration_date=self.today + timedelta(days=10))

        with self.assertRaises(InsufficientStockError):
            decrement_stock_fefo(product=self.product, branch=self.branch, quantity=3)


class DecrementBatchStockConcurrencyTests(TransactionTestCase):
    """Dos descuentos reales y simultáneos sobre un lote con stock justo
    para uno solo: exactamente uno debe ganar, el otro debe fallar limpio
    (no negativo, no oversell) — mismo patrón de hilos reales que
    sales.tests.test_cash_shift.OpenShiftConcurrencyTests."""

    def test_concurrent_decrements_never_oversell(self):
        company = create_company('Abarrotes Don Chuy')
        branch = create_branch(company)
        product = create_product(company)
        batch = create_batch(product, branch, initial_quantity=10)

        results = []

        def attempt():
            try:
                with transaction.atomic():
                    decrement_batch_stock(batch=batch, quantity=10)
                results.append('SOLD')
            except InsufficientStockError:
                results.append('REJECTED')
            finally:
                connection.close()

        t1 = threading.Thread(target=attempt)
        t2 = threading.Thread(target=attempt)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(sorted(results), ['REJECTED', 'SOLD'])
        batch.refresh_from_db()
        self.assertEqual(batch.current_quantity, 0)


class LowStockProductsTests(TestCase):
    """Punto 7: reorder point simplificado sobre Product.min_stock.
    Limitación real ya documentada en el docstring del servicio: solo
    aplica a requires_batch=True, único caso con stock real medido — un
    producto requires_batch=False nunca puede aparecer aquí, sin importar
    su min_stock, porque el sistema no cuenta su stock hoy."""

    def setUp(self):
        self.company = create_company('Abarrotes Don Chuy')
        self.branch = create_branch(self.company)
        self.today = timezone.localdate()

    def test_product_below_min_stock_is_included(self):
        product = create_product(self.company, name='Yogurt', sku='YOG-1', requires_batch=True, min_stock=10)
        create_batch(product, self.branch, initial_quantity=5)

        rows = low_stock_products(company=self.company)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['product_id'], product.id)
        self.assertEqual(rows[0]['current_stock'], 5)
        self.assertEqual(rows[0]['min_stock'], 10)

    def test_product_exactly_at_threshold_is_included(self):
        # <= min_stock, no < min_stock: en el umbral exacto ya cuenta
        # como "hay que reordenar", no solo por debajo.
        product = create_product(self.company, name='Yogurt', sku='YOG-1', requires_batch=True, min_stock=5)
        create_batch(product, self.branch, initial_quantity=5)

        rows = low_stock_products(company=self.company)
        self.assertEqual(len(rows), 1)

    def test_product_with_zero_stock_is_included(self):
        product = create_product(self.company, name='Yogurt', sku='YOG-1', requires_batch=True, min_stock=3)
        create_batch(product, self.branch, initial_quantity=0)

        rows = low_stock_products(company=self.company)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['current_stock'], 0)

    def test_product_above_min_stock_is_excluded(self):
        product = create_product(self.company, name='Yogurt', sku='YOG-1', requires_batch=True, min_stock=5)
        create_batch(product, self.branch, initial_quantity=20)

        self.assertEqual(low_stock_products(company=self.company), [])

    def test_product_not_requiring_batch_is_never_included(self):
        # No tiene ningún stock rastreado (ver docstring de
        # low_stock_products) — aunque min_stock sea alto, no puede
        # aparecer: el sistema no mide nada que comparar.
        create_product(self.company, name='Servicio genérico', sku='SRV-1', requires_batch=False, min_stock=100)

        self.assertEqual(low_stock_products(company=self.company), [])

    def test_expired_batches_do_not_count_toward_current_stock(self):
        # Mismo criterio que decrement_stock_fefo: un lote vencido no es
        # stock vendible, así que no debe hacer que un producto parezca
        # bien abastecido.
        product = create_product(self.company, name='Yogurt', sku='YOG-1', requires_batch=True, min_stock=5)
        create_batch(product, self.branch, batch_number='CADUCADO', initial_quantity=50, expiration_date=self.today - timedelta(days=1))

        rows = low_stock_products(company=self.company)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['current_stock'], 0)

    def test_tenant_isolation(self):
        other_company = create_company('Papelería La Estrella')
        other_branch = create_branch(other_company)
        other_product = create_product(other_company, name='Resistol', sku='RES-1', requires_batch=True, min_stock=10)
        create_batch(other_product, other_branch, initial_quantity=1)

        product = create_product(self.company, name='Yogurt', sku='YOG-1', requires_batch=True, min_stock=10)
        create_batch(product, self.branch, initial_quantity=1)

        rows = low_stock_products(company=self.company)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['product_id'], product.id)
