"""Punto 10 (junto con el punto 9, el de mayor riesgo de esta ronda):
cancelar/devolver una venta ya cobrada vía el mecanismo genérico de
autorización de supervisor (tenants.SupervisorAuthorization) — revierte
stock y cargo a crédito en una sola transacción, sin excepción de rol."""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from audit.models import AuditLog
from catalog.tests.factories import create_batch
from customers.models import CreditMovement
from customers.tests.factories import create_client
from sales.models import Sale
from sales.services import SaleCancellationError, cancel_sale
from sales.tests.factories import create_checkout_context, make_sale
from tenants.models import UserProfile
from tenants.services import request_supervisor_authorization
from tenants.tests.factories import create_user_with_profile


class CancelSaleServiceTests(TestCase):
    def setUp(self):
        self.ctx = create_checkout_context(tax_rate=Decimal('0'))
        self.admin, _ = create_user_with_profile(
            'admin@donchuy.test', self.ctx['branch'], role=UserProfile.Role.ADMINISTRADOR,
        )

    def _token_for(self, requesting_user):
        authorization = request_supervisor_authorization(
            requesting_user=requesting_user, email=self.admin.email, password='testpass123',
        )
        return authorization.token

    def test_cancelling_reverts_batch_stock(self):
        batch = create_batch(self.ctx['product'], self.ctx['branch'], initial_quantity=10)
        sale = make_sale(self.ctx['shift'], self.ctx['product'], batch=batch, quantity=Decimal('3'), unit_price=Decimal('5'))
        batch.refresh_from_db()
        self.assertEqual(batch.current_quantity, 7)

        cancel_sale(sale=sale, actor=self.ctx['user'], supervisor_authorization_token=self._token_for(self.ctx['user']))

        batch.refresh_from_db()
        self.assertEqual(batch.current_quantity, 10)

    def test_cancelling_reverts_credit_charge(self):
        client = create_client(self.ctx['company'], credit_limit=Decimal('200'))
        sale = make_sale(
            self.ctx['shift'], self.ctx['product'], unit_price=Decimal('50'), payment_method='CREDIT', client=client,
        )
        client.credit_account.refresh_from_db()
        self.assertEqual(client.credit_account.balance, Decimal('50.00'))

        cancel_sale(sale=sale, actor=self.ctx['user'], supervisor_authorization_token=self._token_for(self.ctx['user']))

        client.credit_account.refresh_from_db()
        self.assertEqual(client.credit_account.balance, Decimal('0.00'))
        abono = client.credit_account.movements.get(type=CreditMovement.Type.ABONO)
        self.assertEqual(abono.amount, Decimal('50.00'))
        self.assertEqual(abono.sale, sale)

    def test_sets_status_to_refunded(self):
        sale = make_sale(self.ctx['shift'], self.ctx['product'], unit_price=Decimal('10'))
        cancel_sale(sale=sale, actor=self.ctx['user'], supervisor_authorization_token=self._token_for(self.ctx['user']))
        sale.refresh_from_db()
        self.assertEqual(sale.status, Sale.Status.REFUNDED)

    def test_logs_to_audit_log(self):
        sale = make_sale(self.ctx['shift'], self.ctx['product'], unit_price=Decimal('10'))
        cancel_sale(sale=sale, actor=self.ctx['user'], supervisor_authorization_token=self._token_for(self.ctx['user']))

        entry = AuditLog.objects.get(action='sale.cancelled')
        self.assertEqual(entry.user, self.ctx['user'])
        self.assertEqual(entry.object_id, str(sale.id))

    def test_a_sale_with_no_batch_and_no_credit_cancels_cleanly(self):
        # Nada que revertir (venta en efectivo, producto sin lote) — la
        # cancelación igual debe funcionar, no debe asumir que siempre hay
        # algo que deshacer.
        sale = make_sale(self.ctx['shift'], self.ctx['product'], unit_price=Decimal('10'), payment_method='CASH')
        cancel_sale(sale=sale, actor=self.ctx['user'], supervisor_authorization_token=self._token_for(self.ctx['user']))
        sale.refresh_from_db()
        self.assertEqual(sale.status, Sale.Status.REFUNDED)

    def test_cannot_cancel_an_already_refunded_sale(self):
        sale = make_sale(self.ctx['shift'], self.ctx['product'], unit_price=Decimal('10'))
        cancel_sale(sale=sale, actor=self.ctx['user'], supervisor_authorization_token=self._token_for(self.ctx['user']))

        with self.assertRaises(SaleCancellationError):
            cancel_sale(sale=sale, actor=self.ctx['user'], supervisor_authorization_token=self._token_for(self.ctx['user']))

    def test_invalid_token_is_rejected_and_nothing_changes(self):
        batch = create_batch(self.ctx['product'], self.ctx['branch'], initial_quantity=10)
        sale = make_sale(self.ctx['shift'], self.ctx['product'], batch=batch, quantity=Decimal('3'), unit_price=Decimal('5'))

        with self.assertRaises(SaleCancellationError):
            cancel_sale(sale=sale, actor=self.ctx['user'], supervisor_authorization_token='token-invalido')

        sale.refresh_from_db()
        batch.refresh_from_db()
        self.assertEqual(sale.status, Sale.Status.COMPLETED)
        self.assertEqual(batch.current_quantity, 7)

    def test_a_token_requested_by_another_user_cannot_be_used(self):
        other_cajero, _ = create_user_with_profile(
            'otro-cajero@donchuy.test', self.ctx['branch'], capabilities={'handles_cash': True},
        )
        sale = make_sale(self.ctx['shift'], self.ctx['product'], unit_price=Decimal('10'))
        token = self._token_for(other_cajero)

        with self.assertRaises(SaleCancellationError):
            cancel_sale(sale=sale, actor=self.ctx['user'], supervisor_authorization_token=token)
        sale.refresh_from_db()
        self.assertEqual(sale.status, Sale.Status.COMPLETED)

    def test_an_already_used_token_cannot_be_reused(self):
        sale_a = make_sale(self.ctx['shift'], self.ctx['product'], unit_price=Decimal('10'))
        sale_b = make_sale(self.ctx['shift'], self.ctx['product'], unit_price=Decimal('20'))
        token = self._token_for(self.ctx['user'])

        cancel_sale(sale=sale_a, actor=self.ctx['user'], supervisor_authorization_token=token)
        with self.assertRaises(SaleCancellationError):
            cancel_sale(sale=sale_b, actor=self.ctx['user'], supervisor_authorization_token=token)
        sale_b.refresh_from_db()
        self.assertEqual(sale_b.status, Sale.Status.COMPLETED)

    def test_an_expired_token_is_rejected(self):
        sale = make_sale(self.ctx['shift'], self.ctx['product'], unit_price=Decimal('10'))
        authorization = request_supervisor_authorization(
            requesting_user=self.ctx['user'], email=self.admin.email, password='testpass123',
        )
        authorization.expires_at = timezone.now() - timedelta(minutes=1)
        authorization.save(update_fields=['expires_at'])

        with self.assertRaises(SaleCancellationError):
            cancel_sale(sale=sale, actor=self.ctx['user'], supervisor_authorization_token=authorization.token)
        sale.refresh_from_db()
        self.assertEqual(sale.status, Sale.Status.COMPLETED)


class CancelSaleApiTests(APITestCase):
    def setUp(self):
        self.ctx_a = create_checkout_context('Abarrotes Don Chuy', 'Centro', 'cajero@donchuy.test')
        self.ctx_b = create_checkout_context('Papelería La Estrella', 'Norte', 'cajero@estrella.test')
        self.admin_a, _ = create_user_with_profile(
            'admin@donchuy.test', self.ctx_a['branch'], role=UserProfile.Role.ADMINISTRADOR,
        )

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def _token_for(self, requesting_user, supervisor_email):
        response = self.client.post(
            '/api/v1/auth/authorize-exception/',
            {'email': supervisor_email, 'password': 'testpass123'},
            format='json',
        )
        assert response.status_code == status.HTTP_201_CREATED, response.data
        return response.data['token']

    def test_cancel_sale_end_to_end(self):
        sale = make_sale(self.ctx_a['shift'], self.ctx_a['product'], unit_price=Decimal('10'))
        self._auth(self.ctx_a['user'])
        token = self._token_for(self.ctx_a['user'], self.admin_a.email)

        response = self.client.post(
            f'/api/v1/sales/{sale.id}/cancel/', {'supervisor_authorization_token': token}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], Sale.Status.REFUNDED)

    def test_missing_token_is_a_clean_400(self):
        sale = make_sale(self.ctx_a['shift'], self.ctx_a['product'], unit_price=Decimal('10'))
        self._auth(self.ctx_a['user'])
        response = self.client.post(f'/api/v1/sales/{sale.id}/cancel/', {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_token_is_a_clean_400_not_a_500(self):
        sale = make_sale(self.ctx_a['shift'], self.ctx_a['product'], unit_price=Decimal('10'))
        self._auth(self.ctx_a['user'])
        response = self.client.post(
            f'/api/v1/sales/{sale.id}/cancel/', {'supervisor_authorization_token': 'no-existe'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        sale.refresh_from_db()
        self.assertEqual(sale.status, Sale.Status.COMPLETED)

    def test_cannot_cancel_another_tenants_sale(self):
        sale = make_sale(self.ctx_b['shift'], self.ctx_b['product'], unit_price=Decimal('10'))
        self._auth(self.ctx_a['user'])
        token = self._token_for(self.ctx_a['user'], self.admin_a.email)

        response = self.client.post(
            f'/api/v1/sales/{sale.id}/cancel/', {'supervisor_authorization_token': token}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        sale.refresh_from_db()
        self.assertEqual(sale.status, Sale.Status.COMPLETED)

    def test_a_plain_cajero_can_cancel_with_a_valid_token_no_extra_role_needed(self):
        # El gate real es el token, no el rol de quien lo ejecuta — un
        # cajero plano (sin can_authorize_exceptions) puede cancelar
        # siempre que traiga un token válido de alguien con autoridad.
        sale = make_sale(self.ctx_a['shift'], self.ctx_a['product'], unit_price=Decimal('10'))
        self._auth(self.ctx_a['user'])
        token = self._token_for(self.ctx_a['user'], self.admin_a.email)

        response = self.client.post(
            f'/api/v1/sales/{sale.id}/cancel/', {'supervisor_authorization_token': token}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
