import threading
from decimal import Decimal

from django.db import connection, transaction
from django.test import TestCase, TransactionTestCase

from catalog.services import InsufficientStockError, decrement_batch_stock
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
