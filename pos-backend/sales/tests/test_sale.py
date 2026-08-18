"""Sale/SaleDetail/Payment: rediseño real (no extracción), mismo estándar de
tests que CashShift — reglas de negocio, concurrencia real donde aplica
(descuento de stock por lote), y aquí además pago dividido que debe sumar
exacto el total."""
import threading
from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, connection, transaction
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from catalog.tests.factories import create_batch, create_product
from customers.models import CreditMovement
from customers.tests.factories import create_client
from sales.models import CashShift, Payment, Sale, SaleDetail
from sales.services import SaleError, close_shift, create_sale
from sales.tests.factories import create_checkout_context, make_sale


class SaleModelTests(TestCase):
    def setUp(self):
        self.ctx = create_checkout_context()

    def test_client_uuid_is_unique(self):
        from uuid import uuid4
        shared_uuid = uuid4()
        make_sale(self.ctx['shift'], self.ctx['product'], client_uuid=shared_uuid)

        # Un segundo intento con el MISMO client_uuid debe chocar a nivel de
        # BD — es la garantía real de idempotencia para la futura cola
        # offline (dos envíos del mismo POS no deben duplicar la venta).
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Sale.objects.create(
                    cash_shift=self.ctx['shift'],
                    client_uuid=shared_uuid,
                    occurred_at=timezone.now(),
                    subtotal=Decimal('1'), tax_amount=Decimal('0'), total=Decimal('1'),
                )

    def test_occurred_at_is_independent_from_created_at(self):
        past = timezone.now() - timedelta(days=2)
        sale = create_sale(
            cash_shift=self.ctx['shift'],
            details=[{'product': self.ctx['product'], 'batch': None, 'quantity': Decimal('1'), 'unit_price': Decimal('10')}],
            payments=[{'method': 'CASH', 'amount': Decimal('11.60')}],
            occurred_at=past,
        )
        self.assertEqual(sale.occurred_at, past)
        self.assertGreater(sale.created_at, past)

    def test_branch_and_cash_register_are_derived_from_cash_shift(self):
        sale = make_sale(self.ctx['shift'], self.ctx['product'])
        self.assertEqual(sale.branch_id, self.ctx['branch'].id)
        self.assertEqual(sale.cash_register_id, self.ctx['register'].id)
        self.assertEqual(sale.company_id, self.ctx['company'].id)

    def test_sale_detail_batch_is_nullable(self):
        sale = make_sale(self.ctx['shift'], self.ctx['product'], batch=None)
        detail = sale.details.get()
        self.assertIsNone(detail.batch)

    def test_sale_detail_subtotal_property(self):
        sale = make_sale(self.ctx['shift'], self.ctx['product'], quantity=Decimal('3'), unit_price=Decimal('10'))
        detail = sale.details.get()
        self.assertEqual(detail.subtotal, Decimal('30'))


class CreateSaleServiceTests(TestCase):
    def setUp(self):
        self.ctx = create_checkout_context(tax_rate=Decimal('16'))

    def test_single_line_single_payment_happy_path(self):
        sale = create_sale(
            cash_shift=self.ctx['shift'],
            details=[{'product': self.ctx['product'], 'batch': None, 'quantity': Decimal('2'), 'unit_price': Decimal('10.00')}],
            payments=[{'method': 'CASH', 'amount': Decimal('23.20')}],
        )
        self.assertEqual(sale.subtotal, Decimal('20.00'))
        self.assertEqual(sale.tax_amount, Decimal('3.20'))
        self.assertEqual(sale.total, Decimal('23.20'))
        self.assertEqual(sale.status, Sale.Status.COMPLETED)

    def test_payment_reference_is_stored_when_provided(self):
        sale = create_sale(
            cash_shift=self.ctx['shift'],
            details=[{'product': self.ctx['product'], 'batch': None, 'quantity': Decimal('1'), 'unit_price': Decimal('10.00')}],
            payments=[{'method': 'CARD', 'amount': Decimal('11.60'), 'reference': 'AUTH-4521'}],
        )
        self.assertEqual(sale.payments.get().reference, 'AUTH-4521')

    def test_payment_reference_defaults_to_blank_when_omitted(self):
        sale = create_sale(
            cash_shift=self.ctx['shift'],
            details=[{'product': self.ctx['product'], 'batch': None, 'quantity': Decimal('1'), 'unit_price': Decimal('10.00')}],
            payments=[{'method': 'CASH', 'amount': Decimal('11.60')}],
        )
        self.assertEqual(sale.payments.get().reference, '')

    def test_split_payment_across_multiple_methods_matching_total(self):
        sale = create_sale(
            cash_shift=self.ctx['shift'],
            details=[{'product': self.ctx['product'], 'batch': None, 'quantity': Decimal('1'), 'unit_price': Decimal('100.00')}],
            payments=[
                {'method': 'CASH', 'amount': Decimal('50.00')},
                {'method': 'CARD', 'amount': Decimal('66.00')},
            ],
        )
        self.assertEqual(sale.total, Decimal('116.00'))  # 100 + 16% iva
        self.assertEqual(sale.payments.count(), 2)
        self.assertEqual(sum(p.amount for p in sale.payments.all()), sale.total)

    def test_payments_summing_less_than_total_is_rejected(self):
        with self.assertRaises(SaleError):
            create_sale(
                cash_shift=self.ctx['shift'],
                details=[{'product': self.ctx['product'], 'batch': None, 'quantity': Decimal('1'), 'unit_price': Decimal('100.00')}],
                payments=[{'method': 'CASH', 'amount': Decimal('50.00')}],  # faltan 66
            )
        self.assertEqual(Sale.objects.count(), 0)

    def test_payments_summing_more_than_total_is_rejected(self):
        with self.assertRaises(SaleError):
            create_sale(
                cash_shift=self.ctx['shift'],
                details=[{'product': self.ctx['product'], 'batch': None, 'quantity': Decimal('1'), 'unit_price': Decimal('100.00')}],
                payments=[{'method': 'CASH', 'amount': Decimal('200.00')}],
            )
        self.assertEqual(Sale.objects.count(), 0)

    def test_insufficient_stock_error_names_the_product(self):
        batch = create_batch(self.ctx['product'], self.ctx['branch'], initial_quantity=2)
        with self.assertRaises(SaleError) as ctx:
            create_sale(
                cash_shift=self.ctx['shift'],
                details=[{'product': self.ctx['product'], 'batch': batch, 'quantity': Decimal('5'), 'unit_price': Decimal('10.00')}],
                payments=[{'method': 'CASH', 'amount': Decimal('58.00')}],
            )
        self.assertIn(f'No hay suficiente stock de {self.ctx["product"].name}', str(ctx.exception))
        self.assertEqual(Sale.objects.count(), 0)

    def test_rejected_sale_leaves_no_partial_rows_rollback(self):
        # Confirma que el rollback es completo: ni Sale ni SaleDetail ni
        # Payment quedan a medias cuando los pagos no cuadran.
        try:
            create_sale(
                cash_shift=self.ctx['shift'],
                details=[{'product': self.ctx['product'], 'batch': None, 'quantity': Decimal('1'), 'unit_price': Decimal('100.00')}],
                payments=[{'method': 'CASH', 'amount': Decimal('1.00')}],
            )
        except SaleError:
            pass
        self.assertEqual(Sale.objects.count(), 0)
        self.assertEqual(SaleDetail.objects.count(), 0)
        self.assertEqual(Payment.objects.count(), 0)

    def test_no_open_shift_is_rejected(self):
        close_shift(shift=self.ctx['shift'], closing_user=self.ctx['user'], actual_closing_balance=Decimal('0'))
        with self.assertRaises(SaleError):
            make_sale(self.ctx['shift'], self.ctx['product'])

    def test_empty_details_is_rejected(self):
        with self.assertRaises(SaleError):
            create_sale(cash_shift=self.ctx['shift'], details=[], payments=[{'method': 'CASH', 'amount': Decimal('1')}])

    def test_empty_payments_is_rejected(self):
        with self.assertRaises(SaleError):
            create_sale(
                cash_shift=self.ctx['shift'],
                details=[{'product': self.ctx['product'], 'batch': None, 'quantity': Decimal('1'), 'unit_price': Decimal('10')}],
                payments=[],
            )

    def test_batch_not_belonging_to_product_is_rejected(self):
        other_product = create_product(self.ctx['company'], sku='OTRO', tax_rate=Decimal('0'))
        mismatched_batch = create_batch(other_product, self.ctx['branch'])
        with self.assertRaises(SaleError):
            create_sale(
                cash_shift=self.ctx['shift'],
                details=[{
                    'product': self.ctx['product'], 'batch': mismatched_batch,
                    'quantity': Decimal('1'), 'unit_price': Decimal('10'),
                }],
                payments=[{'method': 'CASH', 'amount': Decimal('11.60')}],
            )

    def test_fractional_quantity_for_bulk_unit_types(self):
        granel_product = create_product(
            self.ctx['company'], sku='GRANEL-1', unit_type='KG', tax_rate=Decimal('0'),
        )
        sale = create_sale(
            cash_shift=self.ctx['shift'],
            details=[{
                'product': granel_product, 'batch': None,
                'quantity': Decimal('0.750'), 'unit_price': Decimal('40.00'),
            }],
            payments=[{'method': 'CASH', 'amount': Decimal('30.00')}],
        )
        detail = sale.details.get()
        self.assertEqual(detail.quantity, Decimal('0.750'))
        self.assertEqual(detail.subtotal, Decimal('30.000'))

    def test_mixed_tax_rates_in_same_sale_sum_correctly_at_total(self):
        # Ej. alimento básico exento (0%) + producto gravado (16%) en el
        # mismo ticket — justo el caso que exige calcular el IVA por línea,
        # no solo a nivel de Sale (ver la nota de diseño en SaleDetail).
        exempt_product = create_product(self.ctx['company'], sku='EXENTO', tax_rate=Decimal('0'))
        taxed_product = self.ctx['product']  # tax_rate=16 desde create_checkout_context

        sale = create_sale(
            cash_shift=self.ctx['shift'],
            details=[
                {'product': exempt_product, 'batch': None, 'quantity': Decimal('1'), 'unit_price': Decimal('20.00')},
                {'product': taxed_product, 'batch': None, 'quantity': Decimal('1'), 'unit_price': Decimal('10.00')},
            ],
            payments=[{'method': 'CASH', 'amount': Decimal('31.60')}],
        )
        details = {d.product_id: d for d in sale.details.all()}
        self.assertEqual(details[exempt_product.id].tax_amount, Decimal('0.00'))
        self.assertEqual(details[taxed_product.id].tax_amount, Decimal('1.60'))
        self.assertEqual(sale.tax_amount, Decimal('1.60'))
        self.assertEqual(sale.total, Decimal('31.60'))

    def test_discount_amount_reduces_total(self):
        sale = create_sale(
            cash_shift=self.ctx['shift'],
            details=[{'product': self.ctx['product'], 'batch': None, 'quantity': Decimal('1'), 'unit_price': Decimal('100.00')}],
            payments=[{'method': 'CASH', 'amount': Decimal('106.00')}],
            discount_amount=Decimal('10.00'),
        )
        # 100 subtotal - 10 descuento + 16 iva (sobre subtotal bruto) = 106
        self.assertEqual(sale.discount_amount, Decimal('10.00'))
        self.assertEqual(sale.total, Decimal('106.00'))

    def test_client_uuid_is_generated_when_not_provided(self):
        sale = make_sale(self.ctx['shift'], self.ctx['product'])
        self.assertIsNotNone(sale.client_uuid)

    def test_explicit_client_uuid_is_used_verbatim(self):
        from uuid import uuid4
        given = uuid4()
        sale = make_sale(self.ctx['shift'], self.ctx['product'], client_uuid=given)
        self.assertEqual(sale.client_uuid, given)


class CreateSaleWithBatchTests(TestCase):
    """requires_batch=False no impide vender con batch=None (ya cubierto en
    catalog), y requires_batch=True descuenta stock real del lote elegido."""

    def setUp(self):
        self.ctx = create_checkout_context(tax_rate=Decimal('0'))

    def test_sale_without_batch_does_not_touch_any_batch_stock(self):
        batch = create_batch(self.ctx['product'], self.ctx['branch'], initial_quantity=10)
        make_sale(self.ctx['shift'], self.ctx['product'], batch=None, quantity=Decimal('1'), unit_price=Decimal('5'))
        batch.refresh_from_db()
        self.assertEqual(batch.current_quantity, 10)

    def test_sale_with_batch_decrements_its_stock(self):
        batch = create_batch(self.ctx['product'], self.ctx['branch'], initial_quantity=10)
        make_sale(self.ctx['shift'], self.ctx['product'], batch=batch, quantity=Decimal('3'), unit_price=Decimal('5'))
        batch.refresh_from_db()
        self.assertEqual(batch.current_quantity, 7)

    def test_insufficient_batch_stock_rejects_the_whole_sale(self):
        batch = create_batch(self.ctx['product'], self.ctx['branch'], initial_quantity=2)
        with self.assertRaises(SaleError):
            make_sale(self.ctx['shift'], self.ctx['product'], batch=batch, quantity=Decimal('5'), unit_price=Decimal('5'))
        batch.refresh_from_db()
        self.assertEqual(batch.current_quantity, 2)
        self.assertEqual(Sale.objects.count(), 0)


class CreateSaleWithCreditTests(TestCase):
    """Payment.method=CREDIT conectado con customers — Sale.client, antes
    pospuesto, ya existe (punto 5 del orden de construcción)."""

    def setUp(self):
        self.ctx = create_checkout_context(tax_rate=Decimal('0'))

    def test_credit_payment_without_client_is_rejected(self):
        with self.assertRaises(SaleError):
            make_sale(self.ctx['shift'], self.ctx['product'], unit_price=Decimal('50'), payment_method='CREDIT')
        self.assertEqual(Sale.objects.count(), 0)

    def test_credit_payment_charges_the_client_credit_account(self):
        client = create_client(self.ctx['company'], credit_limit=Decimal('200'))
        sale = make_sale(
            self.ctx['shift'], self.ctx['product'], unit_price=Decimal('50'),
            payment_method='CREDIT', client=client,
        )
        client.credit_account.refresh_from_db()
        self.assertEqual(client.credit_account.balance, Decimal('50.00'))

        movement = client.credit_account.movements.get()
        self.assertEqual(movement.type, CreditMovement.Type.CARGO)
        self.assertEqual(movement.amount, Decimal('50.00'))
        self.assertEqual(movement.sale, sale)

    def test_credit_payment_exceeding_credit_limit_rolls_back_the_whole_sale(self):
        client = create_client(self.ctx['company'], credit_limit=Decimal('10'))
        batch = create_batch(self.ctx['product'], self.ctx['branch'], initial_quantity=5)

        with self.assertRaises(SaleError):
            create_sale(
                cash_shift=self.ctx['shift'],
                client=client,
                details=[{
                    'product': self.ctx['product'], 'batch': batch,
                    'quantity': Decimal('3'), 'unit_price': Decimal('50'),
                }],
                payments=[{'method': 'CREDIT', 'amount': Decimal('150')}],
            )

        # Rollback completo: ni la venta, ni el descuento de stock, ni el
        # cargo a crédito deben quedar aplicados.
        self.assertEqual(Sale.objects.count(), 0)
        batch.refresh_from_db()
        self.assertEqual(batch.current_quantity, 5)
        client.credit_account.refresh_from_db()
        self.assertEqual(client.credit_account.balance, Decimal('0'))
        self.assertEqual(client.credit_account.movements.count(), 0)

    def test_mixed_cash_and_credit_payment_only_charges_the_credit_portion(self):
        client = create_client(self.ctx['company'], credit_limit=Decimal('200'))
        create_sale(
            cash_shift=self.ctx['shift'],
            client=client,
            details=[{
                'product': self.ctx['product'], 'batch': None,
                'quantity': Decimal('1'), 'unit_price': Decimal('100'),
            }],
            payments=[
                {'method': 'CASH', 'amount': Decimal('60')},
                {'method': 'CREDIT', 'amount': Decimal('40')},
            ],
        )
        client.credit_account.refresh_from_db()
        self.assertEqual(client.credit_account.balance, Decimal('40.00'))


class CreateSaleConcurrencyTests(TransactionTestCase):
    """Dos ventas reales y simultáneas contra el mismo lote, con stock
    justo para una sola: exactamente una debe ganar — mismo patrón de
    hilos reales que sales.tests.test_cash_shift.OpenShiftConcurrencyTests
    y catalog.tests.test_services.DecrementBatchStockConcurrencyTests."""

    def test_concurrent_sales_never_oversell_the_same_batch(self):
        ctx = create_checkout_context(tax_rate=Decimal('0'))
        batch = create_batch(ctx['product'], ctx['branch'], initial_quantity=5)

        results = []

        def attempt():
            try:
                create_sale(
                    cash_shift=ctx['shift'],
                    details=[{
                        'product': ctx['product'], 'batch': batch,
                        'quantity': Decimal('5'), 'unit_price': Decimal('10'),
                    }],
                    payments=[{'method': 'CASH', 'amount': Decimal('50')}],
                )
                results.append('SOLD')
            except SaleError:
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
        self.assertEqual(Sale.objects.count(), 1)
