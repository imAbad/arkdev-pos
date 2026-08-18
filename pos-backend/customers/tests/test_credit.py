from decimal import Decimal

from django.test import TestCase

from customers.models import CreditMovement
from customers.services import CreditError, charge_credit, pay_credit
from customers.tests.factories import create_client
from tenants.tests.factories import create_company


class ChargeCreditTests(TestCase):
    def setUp(self):
        self.company = create_company('Abarrotes Don Chuy')
        self.client_ = create_client(self.company, credit_limit=Decimal('200.00'))
        self.account = self.client_.credit_account

    def test_charge_increases_balance(self):
        charge_credit(account=self.account, amount=Decimal('50.00'))
        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, Decimal('50.00'))

    def test_charge_creates_a_cargo_movement(self):
        charge_credit(account=self.account, amount=Decimal('50.00'))
        movement = self.account.movements.get()
        self.assertEqual(movement.type, CreditMovement.Type.CARGO)
        self.assertEqual(movement.amount, Decimal('50.00'))
        self.assertIsNone(movement.sale)

    def test_charge_up_to_exact_credit_limit_is_allowed(self):
        charge_credit(account=self.account, amount=Decimal('200.00'))
        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, Decimal('200.00'))

    def test_charge_exceeding_credit_limit_is_rejected(self):
        with self.assertRaises(CreditError):
            charge_credit(account=self.account, amount=Decimal('201.00'))
        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, Decimal('0'))
        self.assertEqual(self.account.movements.count(), 0)

    def test_charge_exceeding_limit_considers_existing_balance(self):
        charge_credit(account=self.account, amount=Decimal('150.00'))
        with self.assertRaises(CreditError):
            charge_credit(account=self.account, amount=Decimal('51.00'))
        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, Decimal('150.00'))


class PayCreditTests(TestCase):
    def setUp(self):
        self.company = create_company('Abarrotes Don Chuy')
        self.client_ = create_client(self.company, credit_limit=Decimal('200.00'))
        self.account = self.client_.credit_account
        charge_credit(account=self.account, amount=Decimal('120.00'))
        self.account.refresh_from_db()

    def test_abono_without_sale_updates_balance_correctly(self):
        # El caso pedido explícitamente: un abono normal no viene de una
        # venta (sale=None) y aun así debe reflejarse en el balance.
        account = pay_credit(account=self.account, amount=Decimal('50.00'), sale=None)
        self.assertEqual(account.balance, Decimal('70.00'))

        movement = account.movements.get(type=CreditMovement.Type.ABONO)
        self.assertEqual(movement.amount, Decimal('50.00'))
        self.assertIsNone(movement.sale)

    def test_multiple_abonos_accumulate_correctly(self):
        pay_credit(account=self.account, amount=Decimal('20.00'))
        pay_credit(account=self.account, amount=Decimal('30.00'))
        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, Decimal('70.00'))
        self.assertEqual(self.account.movements.filter(type=CreditMovement.Type.ABONO).count(), 2)

    def test_paying_the_full_balance_leaves_it_at_zero(self):
        account = pay_credit(account=self.account, amount=Decimal('120.00'))
        self.assertEqual(account.balance, Decimal('0'))
