from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

from customers.models import Client, CreditAccount
from customers.tests.factories import create_client
from tenants.tests.factories import create_company


class ClientModelTests(TestCase):
    def setUp(self):
        self.company = create_company('Abarrotes Don Chuy')

    def test_creating_a_client_auto_creates_its_credit_account(self):
        client = create_client(self.company)
        self.assertTrue(CreditAccount.objects.filter(client=client).exists())
        self.assertEqual(client.credit_account.balance, Decimal('0'))

    def test_credit_account_company_is_derived_from_client(self):
        client = create_client(self.company)
        self.assertEqual(client.credit_account.company_id, self.company.id)

    def test_credit_account_is_one_to_one(self):
        client = create_client(self.company)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CreditAccount.objects.create(company=self.company, client=client)

    def test_updating_a_client_does_not_create_a_second_account(self):
        client = create_client(self.company, name='Original')
        client.name = 'Actualizado'
        client.save()
        self.assertEqual(CreditAccount.objects.filter(client=client).count(), 1)
