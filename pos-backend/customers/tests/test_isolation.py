"""Aislamiento multi-tenant, permisos y el vector de IDOR vía sale_id en la
acción pay — mismo estándar que el resto del proyecto."""
from decimal import Decimal

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from customers.models import Client, CreditAccount
from customers.services import charge_credit
from customers.tests.factories import create_client
from sales.tests.factories import create_checkout_context, make_sale
from tenants.tests.factories import create_company


class CustomersManagerIsolationTests(TestCase):
    def setUp(self):
        self.company_a = create_company('Abarrotes Don Chuy')
        self.company_b = create_company('Papelería La Estrella')
        self.client_a = create_client(self.company_a)
        self.client_b = create_client(self.company_b)

    def test_for_company_only_returns_own_clients(self):
        self.assertEqual(list(Client.objects.for_company(self.company_a)), [self.client_a])

    def test_for_company_only_returns_own_credit_accounts(self):
        self.assertEqual(
            list(CreditAccount.objects.for_company(self.company_a)),
            [self.client_a.credit_account],
        )

    def test_unscoped_manager_sees_both_tenants(self):
        self.assertEqual(Client.objects.count(), 2)
        self.assertEqual(CreditAccount.objects.count(), 2)


class CustomersApiTests(APITestCase):
    def setUp(self):
        self.ctx_a = create_checkout_context('Abarrotes Don Chuy', 'Centro', 'a@donchuy.test')
        self.ctx_b = create_checkout_context('Papelería La Estrella', 'Norte', 'b@estrella.test')
        self.client_a = create_client(self.ctx_a['company'], credit_limit=Decimal('300'))
        self.client_b = create_client(self.ctx_b['company'], credit_limit=Decimal('300'))

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def test_list_clients_only_returns_own_tenant(self):
        self._auth(self.ctx_a['user'])
        response = self.client.get('/api/v1/clients/')
        ids = [row['id'] for row in response.data['results']]
        self.assertEqual(ids, [self.client_a.id])

    def test_cannot_retrieve_other_tenant_client(self):
        self._auth(self.ctx_a['user'])
        response = self.client.get(f'/api/v1/clients/{self.client_b.id}/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_cannot_retrieve_other_tenant_credit_account(self):
        self._auth(self.ctx_a['user'])
        response = self.client.get(f'/api/v1/credit-accounts/{self.client_b.credit_account.id}/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_pay_endpoint_updates_balance(self):
        charge_credit(account=self.client_a.credit_account, amount=Decimal('100'))
        self._auth(self.ctx_a['user'])
        response = self.client.post(
            f'/api/v1/credit-accounts/{self.client_a.credit_account.id}/pay/',
            {'amount': '40.00'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['balance'], '60.00')

    def test_cannot_pay_other_tenant_credit_account(self):
        charge_credit(account=self.client_b.credit_account, amount=Decimal('100'))
        self._auth(self.ctx_a['user'])
        response = self.client.post(
            f'/api/v1/credit-accounts/{self.client_b.credit_account.id}/pay/',
            {'amount': '40.00'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.client_b.credit_account.refresh_from_db()
        self.assertEqual(self.client_b.credit_account.balance, Decimal('100.00'))

    def test_pay_rejects_sale_id_belonging_to_another_tenant(self):
        # El vector de IDOR que arquitectura_tecnica_pos.md §5 pide vigilar:
        # sale_id resuelto a mano, debe acotarse al tenant igual que
        # cualquier FK cruzado.
        charge_credit(account=self.client_a.credit_account, amount=Decimal('100'))
        sale_b = make_sale(self.ctx_b['shift'], self.ctx_b['product'])
        self._auth(self.ctx_a['user'])
        response = self.client.post(
            f'/api/v1/credit-accounts/{self.client_a.credit_account.id}/pay/',
            {'amount': '40.00', 'sale_id': sale_b.id},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.client_a.credit_account.refresh_from_db()
        self.assertEqual(self.client_a.credit_account.balance, Decimal('100.00'))

    def test_unauthenticated_request_is_rejected(self):
        response = self.client.get('/api/v1/clients/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
