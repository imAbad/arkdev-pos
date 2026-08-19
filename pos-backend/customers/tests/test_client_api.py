"""Observación de sesión (ronda de 4 piezas, punto 3): venta a crédito en
la pantalla de venta — confirmado con evidencia de código que nunca se
construyó (PaymentPanel excluía CREDIT a propósito, comentario explícito
en el componente). El backend (Client/CreditAccount/charge_credit) ya
existía completo; esto agrega lo que la pantalla de venta necesita:
buscar un cliente y ver su crédito disponible real."""
from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from customers.tests.factories import create_client
from customers.services import charge_credit
from tenants.tests.factories import create_full_tenant


class ClientAvailableCreditTests(APITestCase):
    def setUp(self):
        self.tenant = create_full_tenant('Abarrotes Don Chuy', 'Centro', 'admin@donchuy.test')

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def test_available_credit_equals_limit_when_balance_is_zero(self):
        client = create_client(self.tenant['company'], name='Doña Lupe', credit_limit=Decimal('500.00'))
        self._auth(self.tenant['user'])

        response = self.client.get(f'/api/v1/clients/{client.id}/')

        self.assertEqual(response.data['available_credit'], Decimal('500.00'))

    def test_available_credit_reflects_the_real_balance(self):
        client = create_client(self.tenant['company'], name='Doña Lupe', credit_limit=Decimal('500.00'))
        charge_credit(account=client.credit_account, amount=Decimal('120.00'))
        self._auth(self.tenant['user'])

        response = self.client.get(f'/api/v1/clients/{client.id}/')

        self.assertEqual(response.data['available_credit'], Decimal('380.00'))

    def test_search_finds_a_client_by_partial_name(self):
        create_client(self.tenant['company'], name='Doña Lupe')
        create_client(self.tenant['company'], name='Don Pancho')
        self._auth(self.tenant['user'])

        response = self.client.get('/api/v1/clients/', {'search': 'lupe'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = [row['name'] for row in response.data['results']]
        self.assertEqual(names, ['Doña Lupe'])

    def test_search_finds_a_client_by_phone(self):
        create_client(self.tenant['company'], name='Doña Lupe', phone='5551234567')
        create_client(self.tenant['company'], name='Don Pancho', phone='5559876543')
        self._auth(self.tenant['user'])

        response = self.client.get('/api/v1/clients/', {'search': '1234567'})

        names = [row['name'] for row in response.data['results']]
        self.assertEqual(names, ['Doña Lupe'])

    def test_a_plain_cajero_can_create_a_client_for_a_quick_credit_sale(self):
        # Sin gate de rol — el mismo cajero cobrando fiado necesita poder
        # dar de alta un cliente nuevo a mitad de venta.
        self._auth(self.tenant['user'])
        response = self.client.post(
            '/api/v1/clients/', {'name': 'Cliente nuevo', 'phone': '5550001111'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['available_credit'], Decimal('0'))  # sin credit_limit todavía
