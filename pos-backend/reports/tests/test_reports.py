"""Reportes: agregaciones de solo lectura sobre datos reales de
sales/catalog — mismo estándar que el resto del proyecto (queryset
directo Y API real, aislamiento multi-tenant probado explícito)."""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from catalog.models import InventoryAdjustment
from catalog.services import adjust_batch_stock
from catalog.tests.factories import create_batch, create_category, create_product
from customers.models import CreditMovement
from customers.services import pay_credit
from customers.tests.factories import create_client
from reports import services
from sales.services import close_shift, compute_expected_totals, open_shift
from sales.tests.factories import create_cash_register, create_checkout_context, make_sale
from tenants.tests.factories import create_full_tenant, create_user_with_profile
from tenants.models import UserProfile


class SalesByProductServiceTests(TestCase):
    def setUp(self):
        self.ctx = create_checkout_context(tax_rate=Decimal('16'))
        self.today = timezone.localdate()

    def test_aggregates_quantity_and_revenue_grouped_by_product(self):
        make_sale(self.ctx['shift'], self.ctx['product'], quantity=Decimal('2'), unit_price=Decimal('10.00'))
        make_sale(self.ctx['shift'], self.ctx['product'], quantity=Decimal('3'), unit_price=Decimal('10.00'))

        rows = services.sales_by_product(
            company=self.ctx['company'], date_from=self.today, date_to=self.today,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['product_id'], self.ctx['product'].id)
        self.assertEqual(rows[0]['quantity_sold'], Decimal('5'))
        self.assertEqual(rows[0]['revenue'], Decimal('50.00'))

    def test_grouped_by_category_sums_across_products(self):
        category = create_category(self.ctx['company'], name='Abarrotes')
        product_a = create_product(self.ctx['company'], category=category, name='A', sku='A-1')
        product_b = create_product(self.ctx['company'], category=category, name='B', sku='B-1')
        make_sale(self.ctx['shift'], product_a, quantity=Decimal('1'), unit_price=Decimal('10.00'))
        make_sale(self.ctx['shift'], product_b, quantity=Decimal('1'), unit_price=Decimal('20.00'))

        rows = services.sales_by_product(
            company=self.ctx['company'], date_from=self.today, date_to=self.today, group_by='category',
        )
        abarrotes_row = next(r for r in rows if r['category_name'] == 'Abarrotes')
        self.assertEqual(abarrotes_row['revenue'], Decimal('30.00'))

    def test_excludes_sales_outside_the_date_range(self):
        make_sale(self.ctx['shift'], self.ctx['product'], quantity=Decimal('1'), unit_price=Decimal('10.00'))

        rows = services.sales_by_product(
            company=self.ctx['company'],
            date_from=self.today - timedelta(days=10),
            date_to=self.today - timedelta(days=1),
        )
        self.assertEqual(rows, [])

    def test_excludes_sales_from_a_different_branch(self):
        make_sale(self.ctx['shift'], self.ctx['product'], quantity=Decimal('1'), unit_price=Decimal('10.00'))
        other_ctx = create_checkout_context('Otra tienda', 'Sur', 'otra@sur.test')

        rows = services.sales_by_product(
            company=self.ctx['company'], date_from=self.today, date_to=self.today, branch=other_ctx['branch'],
        )
        self.assertEqual(rows, [])

    def test_grouped_by_cashier_splits_revenue_per_seller(self):
        # Punto 2: trazabilidad de vendedor — el dato ya existía en la
        # cadena Sale -> CashShift -> user, esto solo la expone agrupada.
        other_user, _ = create_user_with_profile(
            'otro-cajero@donchuy.test', self.ctx['branch'], capabilities={'handles_cash': True},
        )
        other_shift = open_shift(user=other_user, cash_register=create_cash_register(self.ctx['branch'], name='Caja 2'))

        make_sale(self.ctx['shift'], self.ctx['product'], quantity=Decimal('1'), unit_price=Decimal('10.00'))
        make_sale(other_shift, self.ctx['product'], quantity=Decimal('1'), unit_price=Decimal('50.00'))

        rows = services.sales_by_product(
            company=self.ctx['company'], date_from=self.today, date_to=self.today, group_by='cashier',
        )
        by_email = {row['cashier_email']: row['revenue'] for row in rows}
        self.assertEqual(by_email[self.ctx['user'].email], Decimal('10.00'))  # revenue = subtotal, no incluye iva (columna aparte)
        self.assertEqual(by_email['otro-cajero@donchuy.test'], Decimal('50.00'))

    def test_cashier_filter_scopes_product_grouping_to_one_seller(self):
        other_user, _ = create_user_with_profile(
            'otro-cajero@donchuy.test', self.ctx['branch'], capabilities={'handles_cash': True},
        )
        other_shift = open_shift(user=other_user, cash_register=create_cash_register(self.ctx['branch'], name='Caja 2'))

        make_sale(self.ctx['shift'], self.ctx['product'], quantity=Decimal('1'), unit_price=Decimal('10.00'))
        make_sale(other_shift, self.ctx['product'], quantity=Decimal('1'), unit_price=Decimal('50.00'))

        rows = services.sales_by_product(
            company=self.ctx['company'], date_from=self.today, date_to=self.today, cashier=other_user,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['revenue'], Decimal('50.00'))


class InventoryValuationServiceTests(TestCase):
    def setUp(self):
        self.ctx = create_checkout_context()

    def test_values_stock_at_cost_price_not_sale_price(self):
        product = create_product(
            self.ctx['company'], name='Arroz', sku='ARROZ-1', cost_price=Decimal('8.00'), sale_price=Decimal('12.00'),
        )
        create_batch(product, self.ctx['branch'], initial_quantity=10)

        rows = services.inventory_valuation(company=self.ctx['company'])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['quantity'], 10)
        self.assertEqual(rows[0]['valuation'], Decimal('80.00'))

    def test_excludes_expired_batches(self):
        product = create_product(self.ctx['company'], sku='PROD-EXP', cost_price=Decimal('8.00'))
        create_batch(product, self.ctx['branch'], expiration_date=timezone.localdate() - timedelta(days=1))

        rows = services.inventory_valuation(company=self.ctx['company'])
        self.assertEqual(rows, [])

    def test_excludes_batches_with_no_remaining_stock(self):
        product = create_product(self.ctx['company'], sku='PROD-SOLDOUT', cost_price=Decimal('8.00'))
        batch = create_batch(product, self.ctx['branch'], initial_quantity=5)
        batch.current_quantity = 0
        batch.save(update_fields=['current_quantity'])

        rows = services.inventory_valuation(company=self.ctx['company'])
        self.assertEqual(rows, [])


class ExpiredStockReportServiceTests(TestCase):
    def setUp(self):
        self.ctx = create_checkout_context()

    def test_lists_only_expired_batches_with_remaining_stock(self):
        product = create_product(self.ctx['company'], name='Yogurt', sku='YOGURT-1', cost_price=Decimal('5.00'))
        expired = create_batch(
            product, self.ctx['branch'], batch_number='VENCIDO',
            initial_quantity=4, expiration_date=timezone.localdate() - timedelta(days=3),
        )
        create_batch(
            product, self.ctx['branch'], batch_number='VIGENTE',
            initial_quantity=4, expiration_date=timezone.localdate() + timedelta(days=30),
        )

        rows = services.expired_stock_report(company=self.ctx['company'])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['batch_id'], expired.id)
        self.assertEqual(rows[0]['quantity'], 4)
        self.assertEqual(rows[0]['valuation'], Decimal('20.00'))

    def test_excludes_expired_batches_already_sold_out(self):
        product = create_product(self.ctx['company'], sku='PROD-EXP-SOLDOUT', cost_price=Decimal('5.00'))
        batch = create_batch(
            product, self.ctx['branch'], expiration_date=timezone.localdate() - timedelta(days=3),
        )
        batch.current_quantity = 0
        batch.save(update_fields=['current_quantity'])

        rows = services.expired_stock_report(company=self.ctx['company'])
        self.assertEqual(rows, [])


class NearExpiryStockReportServiceTests(TestCase):
    def setUp(self):
        self.ctx = create_checkout_context()
        self.today = timezone.localdate()

    def test_lists_batches_expiring_within_the_window_ordered_soonest_first(self):
        product = create_product(self.ctx['company'], name='Yogurt', sku='YOGURT-NE', cost_price=Decimal('5.00'))
        soon = create_batch(product, self.ctx['branch'], batch_number='EN-3-DIAS', initial_quantity=4, expiration_date=self.today + timedelta(days=3))
        later = create_batch(product, self.ctx['branch'], batch_number='EN-6-DIAS', initial_quantity=2, expiration_date=self.today + timedelta(days=6))

        rows = services.near_expiry_stock_report(company=self.ctx['company'], days=7)
        self.assertEqual([r['batch_id'] for r in rows], [soon.id, later.id])
        self.assertEqual(rows[0]['days_to_expire'], 3)

    def test_excludes_batches_outside_the_window(self):
        product = create_product(self.ctx['company'], sku='PROD-LEJOS', cost_price=Decimal('5.00'))
        create_batch(product, self.ctx['branch'], expiration_date=self.today + timedelta(days=20))

        rows = services.near_expiry_stock_report(company=self.ctx['company'], days=7)
        self.assertEqual(rows, [])

    def test_excludes_already_expired_batches(self):
        # Esos van en expired_stock_report, no se duplican aquí.
        product = create_product(self.ctx['company'], sku='PROD-VENCIDO', cost_price=Decimal('5.00'))
        create_batch(product, self.ctx['branch'], expiration_date=self.today - timedelta(days=1))

        rows = services.near_expiry_stock_report(company=self.ctx['company'], days=7)
        self.assertEqual(rows, [])

    def test_window_is_configurable(self):
        product = create_product(self.ctx['company'], sku='PROD-14', cost_price=Decimal('5.00'))
        batch = create_batch(product, self.ctx['branch'], expiration_date=self.today + timedelta(days=14))

        self.assertEqual(services.near_expiry_stock_report(company=self.ctx['company'], days=7), [])
        rows_30 = services.near_expiry_stock_report(company=self.ctx['company'], days=30)
        self.assertEqual([r['batch_id'] for r in rows_30], [batch.id])


class CashShiftClosuresServiceTests(TestCase):
    def setUp(self):
        self.ctx = create_checkout_context()
        self.today = timezone.localdate()

    def test_lists_closed_shifts_with_their_difference(self):
        make_sale(self.ctx['shift'], self.ctx['product'], quantity=Decimal('1'), unit_price=Decimal('100.00'))
        expected = compute_expected_totals(self.ctx['shift'])
        close_shift(
            shift=self.ctx['shift'], closing_user=self.ctx['user'],
            actual_closing_balance=expected['cash'] - Decimal('5.00'),
            actual_voucher_total=expected['voucher'],
        )

        rows = services.cash_shift_closures(company=self.ctx['company'], date_from=self.today, date_to=self.today)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['id'], self.ctx['shift'].id)
        self.assertEqual(rows[0]['cash_difference'], Decimal('-5.00'))

    def test_excludes_shifts_still_open(self):
        rows = services.cash_shift_closures(company=self.ctx['company'], date_from=self.today, date_to=self.today)
        self.assertEqual(rows, [])


class CashShiftDetailServiceTests(TestCase):
    """Observación de sesión (ronda "3 piezas", punto 3): drill-down de un
    solo turno — cada sección se contrasta contra lo que ya quedó
    guardado en la base de datos (Sale/Payment/CreditMovement), no un
    cálculo paralelo."""

    def setUp(self):
        self.ctx = create_checkout_context(tax_rate=Decimal('16'))

    def _close(self, actual_closing_balance=None, actual_voucher_total=None):
        expected = compute_expected_totals(self.ctx['shift'])
        return close_shift(
            shift=self.ctx['shift'], closing_user=self.ctx['user'],
            actual_closing_balance=actual_closing_balance if actual_closing_balance is not None else expected['cash'],
            actual_voucher_total=actual_voucher_total if actual_voucher_total is not None else expected['voucher'],
        )

    def test_sales_count_and_total_match_the_shifts_own_sales(self):
        make_sale(self.ctx['shift'], self.ctx['product'], quantity=Decimal('1'), unit_price=Decimal('100.00'))
        make_sale(self.ctx['shift'], self.ctx['product'], quantity=Decimal('1'), unit_price=Decimal('50.00'))
        # Venta de OTRO turno — no debe colarse en el detalle de este.
        other_ctx = create_checkout_context('Otra tienda', 'Sur', 'otra@sur.test')
        make_sale(other_ctx['shift'], other_ctx['product'], unit_price=Decimal('999.00'))
        self._close()

        data = services.cash_shift_detail(company=self.ctx['company'], shift=self.ctx['shift'])
        self.assertEqual(data['sales_count'], 2)
        self.assertEqual(data['sales_total'], Decimal('174.00'))  # (100+50) * 1.16

    def test_payments_by_method_breakdown_matches_actual_payments(self):
        make_sale(self.ctx['shift'], self.ctx['product'], unit_price=Decimal('100.00'), payment_method='CASH')
        make_sale(self.ctx['shift'], self.ctx['product'], unit_price=Decimal('50.00'), payment_method='CARD')
        self._close()

        data = services.cash_shift_detail(company=self.ctx['company'], shift=self.ctx['shift'])
        by_method = {row['method']: row['total'] for row in data['payments_by_method']}
        self.assertEqual(by_method['CASH'], Decimal('116.00'))
        self.assertEqual(by_method['CARD'], Decimal('58.00'))
        labels = {row['method']: row['method_label'] for row in data['payments_by_method']}
        self.assertEqual(labels['CASH'], 'Efectivo')
        self.assertEqual(labels['CARD'], 'Tarjeta')

    def test_arqueo_fields_come_straight_from_the_shift_model_not_recalculated(self):
        make_sale(self.ctx['shift'], self.ctx['product'], unit_price=Decimal('100.00'))
        expected = compute_expected_totals(self.ctx['shift'])
        self._close(actual_closing_balance=expected['cash'] - Decimal('5.00'))

        data = services.cash_shift_detail(company=self.ctx['company'], shift=self.ctx['shift'])
        self.assertEqual(data['opening_balance'], self.ctx['shift'].opening_balance)
        self.assertEqual(data['expected_closing_balance'], self.ctx['shift'].expected_closing_balance)
        self.assertEqual(data['actual_closing_balance'], self.ctx['shift'].actual_closing_balance)
        self.assertEqual(data['cash_difference'], Decimal('-5.00'))

    def test_credit_payments_received_during_the_shift_are_included(self):
        client = create_client(self.ctx['company'], credit_limit=Decimal('500'))
        pay_credit(account=client.credit_account, amount=Decimal('80.00'))
        self._close()

        data = services.cash_shift_detail(company=self.ctx['company'], shift=self.ctx['shift'])
        self.assertEqual(len(data['credit_payments']), 1)
        self.assertEqual(data['credit_payments'][0]['client_name'], client.name)
        self.assertEqual(data['credit_payments'][0]['amount'], Decimal('80.00'))
        self.assertEqual(data['credit_payments_total'], Decimal('80.00'))

    def test_credit_payments_outside_the_shift_window_are_excluded(self):
        client = create_client(self.ctx['company'], credit_limit=Decimal('500'))
        pay_credit(account=client.credit_account, amount=Decimal('80.00'))
        self._close()
        movement = CreditMovement.objects.get(account=client.credit_account)
        CreditMovement.objects.filter(pk=movement.pk).update(
            created_at=self.ctx['shift'].opened_at - timedelta(hours=1),
        )

        data = services.cash_shift_detail(company=self.ctx['company'], shift=self.ctx['shift'])
        self.assertEqual(data['credit_payments'], [])
        self.assertEqual(data['credit_payments_total'], Decimal('0'))

    def test_shift_with_no_sales_or_credit_payments_reports_zeroes_not_an_error(self):
        self._close()
        data = services.cash_shift_detail(company=self.ctx['company'], shift=self.ctx['shift'])
        self.assertEqual(data['sales_count'], 0)
        self.assertEqual(data['sales_total'], Decimal('0'))
        self.assertEqual(data['payments_by_method'], [])
        self.assertEqual(data['credit_payments'], [])


class CashShiftDetailApiTests(APITestCase):
    def setUp(self):
        self.ctx = create_checkout_context()
        self.admin, _ = create_user_with_profile(
            'admin@donchuy.test', self.ctx['branch'], role=UserProfile.Role.ADMINISTRADOR,
        )

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def test_returns_the_detail_of_a_closed_shift(self):
        make_sale(self.ctx['shift'], self.ctx['product'], unit_price=Decimal('100.00'))
        close_shift(shift=self.ctx['shift'], closing_user=self.ctx['user'], actual_closing_balance=Decimal('0'))
        self._auth(self.admin)

        response = self.client.get('/api/v1/reports/cash-shift-detail/', {'shift': self.ctx['shift'].id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['shift_id'], self.ctx['shift'].id)
        self.assertEqual(response.data['sales_count'], 1)

    def test_an_open_shift_is_rejected_with_a_clear_400(self):
        self._auth(self.admin)
        response = self.client.get('/api/v1/reports/cash-shift-detail/', {'shift': self.ctx['shift'].id})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_shift_from_another_tenant_is_404_not_leaked(self):
        other_ctx = create_checkout_context('Otro tenant', 'Norte', 'otro@norte.test')
        close_shift(shift=other_ctx['shift'], closing_user=other_ctx['user'], actual_closing_balance=Decimal('0'))
        self._auth(self.admin)

        response = self.client.get('/api/v1/reports/cash-shift-detail/', {'shift': other_ctx['shift'].id})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_plain_cajero_is_denied(self):
        close_shift(shift=self.ctx['shift'], closing_user=self.ctx['user'], actual_closing_balance=Decimal('0'))
        self._auth(self.ctx['user'])  # handles_cash=True, sin can_authorize_exceptions
        response = self.client.get('/api/v1/reports/cash-shift-detail/', {'shift': self.ctx['shift'].id})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class InventoryAdjustmentsReportServiceTests(TestCase):
    """Observación de sesión (ronda de 4 piezas, punto 4): el motivo de
    cada ajuste manual de stock debe verse en algún reporte, no quedar
    enterrado solo en la base de datos."""

    def setUp(self):
        self.ctx = create_checkout_context()
        self.today = timezone.localdate()

    def test_lists_adjustments_with_reason_and_who(self):
        product = create_product(self.ctx['company'], sku='ADJ-1', requires_batch=True)
        batch = create_batch(product, self.ctx['branch'], initial_quantity=10)
        adjust_batch_stock(
            batch=batch, quantity_delta=-3, reason=InventoryAdjustment.Reason.DAMAGE, actor=self.ctx['user'],
        )

        rows = services.inventory_adjustments(company=self.ctx['company'], date_from=self.today, date_to=self.today)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['product_name'], product.name)
        self.assertEqual(rows[0]['quantity_delta'], -3)
        self.assertEqual(rows[0]['quantity_before'], 10)
        self.assertEqual(rows[0]['quantity_after'], 7)
        self.assertEqual(rows[0]['reason_label'], 'Merma/rotura')
        self.assertEqual(rows[0]['user_email'], self.ctx['user'].email)

    def test_other_reason_includes_the_free_text_detail(self):
        product = create_product(self.ctx['company'], sku='ADJ-2', requires_batch=True)
        batch = create_batch(product, self.ctx['branch'], initial_quantity=5)
        adjust_batch_stock(
            batch=batch, quantity_delta=-1, reason=InventoryAdjustment.Reason.OTHER,
            actor=self.ctx['user'], reason_detail='Se mojó en bodega',
        )

        rows = services.inventory_adjustments(company=self.ctx['company'], date_from=self.today, date_to=self.today)
        self.assertEqual(rows[0]['reason_detail'], 'Se mojó en bodega')

    def test_excludes_adjustments_outside_the_date_range(self):
        product = create_product(self.ctx['company'], sku='ADJ-3', requires_batch=True)
        batch = create_batch(product, self.ctx['branch'], initial_quantity=10)
        adjust_batch_stock(
            batch=batch, quantity_delta=-1, reason=InventoryAdjustment.Reason.DAMAGE, actor=self.ctx['user'],
        )

        rows = services.inventory_adjustments(
            company=self.ctx['company'],
            date_from=self.today - timedelta(days=10),
            date_to=self.today - timedelta(days=1),
        )
        self.assertEqual(rows, [])

    def test_excludes_adjustments_from_a_different_branch(self):
        other_ctx = create_checkout_context('Otra tienda', 'Sur', 'otra@sur.test')
        product = create_product(other_ctx['company'], sku='ADJ-4', requires_batch=True)
        batch = create_batch(product, other_ctx['branch'], initial_quantity=10)
        adjust_batch_stock(
            batch=batch, quantity_delta=-1, reason=InventoryAdjustment.Reason.DAMAGE, actor=other_ctx['user'],
        )

        rows = services.inventory_adjustments(
            company=other_ctx['company'], date_from=self.today, date_to=self.today, branch=self.ctx['branch'],
        )
        self.assertEqual(rows, [])


class InventoryAdjustmentsReportApiTests(APITestCase):
    def setUp(self):
        self.ctx = create_checkout_context()
        self.today = timezone.localdate()
        self.admin, _ = create_user_with_profile(
            'admin@donchuy.test', self.ctx['branch'], role=UserProfile.Role.ADMINISTRADOR,
        )

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def test_administrador_can_read_the_report(self):
        product = create_product(self.ctx['company'], sku='ADJ-API-1', requires_batch=True)
        batch = create_batch(product, self.ctx['branch'], initial_quantity=10)
        adjust_batch_stock(
            batch=batch, quantity_delta=-2, reason=InventoryAdjustment.Reason.COUNT_CORRECTION, actor=self.admin,
        )
        self._auth(self.admin)

        response = self.client.get(
            '/api/v1/reports/inventory-adjustments/', {'date_from': self.today, 'date_to': self.today},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['reason_label'], 'Corrección de conteo')

    def test_plain_cajero_is_denied(self):
        self._auth(self.ctx['user'])
        response = self.client.get(
            '/api/v1/reports/inventory-adjustments/', {'date_from': self.today, 'date_to': self.today},
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class ReportsApiPermissionTests(APITestCase):
    def setUp(self):
        self.ctx = create_checkout_context()
        self.today = timezone.localdate()

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def test_cajero_without_administrador_role_is_denied(self):
        self._auth(self.ctx['user'])  # CAJERO por default en create_checkout_context
        response = self.client.get(
            '/api/v1/reports/sales-by-product/',
            {'date_from': self.today, 'date_to': self.today},
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_cajero_with_can_authorize_exceptions_can_read_all_four_reports(self):
        from tenants.tests.factories import create_user_with_profile
        supervisor, _ = create_user_with_profile(
            'supervisor@donchuy.test', self.ctx['branch'],
            role=UserProfile.Role.CAJERO, capabilities={'can_authorize_exceptions': True},
        )
        self._auth(supervisor)

        endpoints = [
            ('/api/v1/reports/sales-by-product/', {'date_from': self.today, 'date_to': self.today}),
            ('/api/v1/reports/inventory-valuation/', {}),
            ('/api/v1/reports/expired-stock/', {}),
            ('/api/v1/reports/cash-shift-closures/', {'date_from': self.today, 'date_to': self.today}),
        ]
        for url, params in endpoints:
            response = self.client.get(url, params)
            self.assertEqual(response.status_code, status.HTTP_200_OK, f'{url} -> {response.status_code}')

    def test_cajero_without_can_authorize_exceptions_still_gets_403(self):
        self._auth(self.ctx['user'])  # handles_cash=True pero sin can_authorize_exceptions
        response = self.client.get(
            '/api/v1/reports/sales-by-product/',
            {'date_from': self.today, 'date_to': self.today},
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_administrador_can_read_the_report(self):
        admin_user, _ = self._make_admin()
        self._auth(admin_user)
        response = self.client.get(
            '/api/v1/reports/sales-by-product/',
            {'date_from': self.today, 'date_to': self.today},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_branch_from_another_tenant_is_rejected_not_silently_ignored(self):
        admin_user, _ = self._make_admin()
        other_ctx = create_checkout_context('Otro tenant', 'Norte', 'otro@norte.test')
        self._auth(admin_user)

        response = self.client.get(
            '/api/v1/reports/sales-by-product/',
            {'date_from': self.today, 'date_to': self.today, 'branch': other_ctx['branch'].id},
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_cash_shift_closures_report_reflects_the_real_difference_over_the_api(self):
        make_sale(self.ctx['shift'], self.ctx['product'], quantity=Decimal('1'), unit_price=Decimal('100.00'))
        expected = compute_expected_totals(self.ctx['shift'])
        close_shift(
            shift=self.ctx['shift'], closing_user=self.ctx['user'],
            actual_closing_balance=expected['cash'] + Decimal('3.00'),
            actual_voucher_total=expected['voucher'],
        )
        admin_user, _ = self._make_admin()
        self._auth(admin_user)

        response = self.client.get(
            '/api/v1/reports/cash-shift-closures/',
            {'date_from': self.today, 'date_to': self.today},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[0]['cash_difference'], Decimal('3.00'))

    def test_near_expiry_stock_report_over_the_api_with_custom_window(self):
        product = create_product(self.ctx['company'], name='Yogurt', sku='YOGURT-API', cost_price=Decimal('5.00'))
        create_batch(product, self.ctx['branch'], batch_number='EN-10', initial_quantity=3, expiration_date=self.today + timedelta(days=10))
        admin_user, _ = self._make_admin()
        self._auth(admin_user)

        default_response = self.client.get('/api/v1/reports/near-expiry-stock/')
        self.assertEqual(default_response.status_code, status.HTTP_200_OK)
        self.assertEqual(default_response.data, [])  # fuera de los 7 días default

        wide_response = self.client.get('/api/v1/reports/near-expiry-stock/', {'days': 15})
        self.assertEqual(wide_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(wide_response.data), 1)
        self.assertEqual(wide_response.data[0]['days_to_expire'], 10)

    def _make_admin(self):
        from tenants.tests.factories import create_user_with_profile
        return create_user_with_profile(
            'admin@donchuy.test', self.ctx['branch'], role=UserProfile.Role.ADMINISTRADOR,
        )
