"""Reportes: agregaciones de solo lectura sobre datos reales de
sales/catalog — mismo estándar que el resto del proyecto (queryset
directo Y API real, aislamiento multi-tenant probado explícito)."""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from catalog.tests.factories import create_batch, create_category, create_product
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
