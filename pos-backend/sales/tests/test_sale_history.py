"""Observación de sesión, punto 2: historial de ventas navegable
(frontend nuevo) necesitaba filtrar por fecha y saber quién cobró —
ninguno de los dos existía en el endpoint de solo lectura antes de esto."""
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from sales.tests.factories import create_checkout_context, make_sale
from tenants.models import UserProfile
from tenants.tests.factories import create_user_with_profile


class SaleHistoryApiTests(APITestCase):
    def setUp(self):
        self.ctx = create_checkout_context()
        self.admin, _ = create_user_with_profile(
            'admin@donchuy.test', self.ctx['branch'], role=UserProfile.Role.ADMINISTRADOR,
        )
        self.today = timezone.localdate()

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def test_includes_cashier_email(self):
        make_sale(self.ctx['shift'], self.ctx['product'], unit_price=Decimal('10.00'))
        self._auth(self.admin)
        response = self.client.get('/api/v1/sales/')
        self.assertEqual(response.data['results'][0]['cashier_email'], self.ctx['user'].email)

    def test_orders_most_recent_first(self):
        first = make_sale(self.ctx['shift'], self.ctx['product'], unit_price=Decimal('10.00'))
        first.occurred_at = timezone.now() - timedelta(days=2)
        first.save(update_fields=['occurred_at'])
        second = make_sale(self.ctx['shift'], self.ctx['product'], unit_price=Decimal('20.00'))

        self._auth(self.admin)
        response = self.client.get('/api/v1/sales/')
        ids = [row['id'] for row in response.data['results']]
        self.assertEqual(ids, [second.id, first.id])

    def test_filters_by_date_range(self):
        old_sale = make_sale(self.ctx['shift'], self.ctx['product'], unit_price=Decimal('10.00'))
        old_sale.occurred_at = timezone.now() - timedelta(days=10)
        old_sale.save(update_fields=['occurred_at'])
        recent_sale = make_sale(self.ctx['shift'], self.ctx['product'], unit_price=Decimal('20.00'))

        self._auth(self.admin)
        response = self.client.get(
            '/api/v1/sales/', {'date_from': self.today - timedelta(days=1), 'date_to': self.today},
        )
        ids = [row['id'] for row in response.data['results']]
        self.assertEqual(ids, [recent_sale.id])

    def test_without_date_params_returns_everything(self):
        old_sale = make_sale(self.ctx['shift'], self.ctx['product'], unit_price=Decimal('10.00'))
        old_sale.occurred_at = timezone.now() - timedelta(days=100)
        old_sale.save(update_fields=['occurred_at'])
        recent_sale = make_sale(self.ctx['shift'], self.ctx['product'], unit_price=Decimal('20.00'))

        self._auth(self.admin)
        response = self.client.get('/api/v1/sales/')
        ids = {row['id'] for row in response.data['results']}
        self.assertEqual(ids, {old_sale.id, recent_sale.id})
