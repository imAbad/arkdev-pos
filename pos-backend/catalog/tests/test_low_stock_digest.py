"""Punto 7: resumen diario de stock bajo por correo — servicio de armado
del correo (catalog/emails.py) y el management command que decide a quién
mandarlo (send_low_stock_digest), mismo estándar que sales/tests/test_emails.py."""
from io import StringIO
from unittest.mock import patch

from django.core import mail
from django.core.management import call_command
from django.test import TestCase

from catalog.emails import LowStockDigestEmailError, send_low_stock_digest_email
from catalog.tests.factories import create_batch, create_product
from tenants.models import UserProfile
from tenants.tests.factories import create_full_tenant, create_user_with_profile


class SendLowStockDigestEmailTests(TestCase):
    def test_sends_an_email_listing_every_row(self):
        rows = [
            {'product_id': 1, 'product_name': 'Yogurt natural 1L', 'sku': 'YOG-1', 'current_stock': 2, 'min_stock': 10},
        ]
        send_low_stock_digest_email(business_name='Abarrotes Don Chuy', to_email='admin@donchuy.test', rows=rows)

        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertEqual(sent.to, ['admin@donchuy.test'])
        self.assertIn('Yogurt natural 1L', sent.body)
        self.assertIn('YOG-1', sent.body)

    def test_raises_human_error_when_smtp_fails(self):
        with patch('django.core.mail.message.EmailMessage.send', side_effect=OSError('conexión rechazada')):
            with self.assertRaises(LowStockDigestEmailError):
                send_low_stock_digest_email(
                    business_name='Abarrotes Don Chuy', to_email='admin@donchuy.test',
                    rows=[{'product_id': 1, 'product_name': 'X', 'sku': 'X', 'current_stock': 0, 'min_stock': 1}],
                )
        self.assertEqual(len(mail.outbox), 0)


class SendLowStockDigestCommandTests(TestCase):
    def test_sends_one_email_per_administrador_when_tenant_has_low_stock(self):
        tenant = create_full_tenant('Abarrotes Don Chuy', 'Centro', 'admin@donchuy.test', role=UserProfile.Role.ADMINISTRADOR)
        create_user_with_profile('otro-admin@donchuy.test', tenant['branch'], role=UserProfile.Role.ADMINISTRADOR)
        product = create_product(tenant['company'], name='Yogurt', sku='YOG-1', requires_batch=True, min_stock=10)
        create_batch(product, tenant['branch'], initial_quantity=1)

        call_command('send_low_stock_digest', stdout=StringIO())

        self.assertEqual(len(mail.outbox), 2)
        recipients = sorted(m.to[0] for m in mail.outbox)
        self.assertEqual(recipients, ['admin@donchuy.test', 'otro-admin@donchuy.test'])

    def test_does_not_email_a_cajero(self):
        tenant = create_full_tenant('Abarrotes Don Chuy', 'Centro', 'admin@donchuy.test', role=UserProfile.Role.ADMINISTRADOR)
        create_user_with_profile('cajero@donchuy.test', tenant['branch'], role=UserProfile.Role.CAJERO)
        product = create_product(tenant['company'], name='Yogurt', sku='YOG-1', requires_batch=True, min_stock=10)
        create_batch(product, tenant['branch'], initial_quantity=1)

        call_command('send_low_stock_digest', stdout=StringIO())

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['admin@donchuy.test'])

    def test_no_email_for_a_tenant_with_zero_low_stock_items(self):
        tenant = create_full_tenant('Abarrotes Don Chuy', 'Centro', 'admin@donchuy.test', role=UserProfile.Role.ADMINISTRADOR)
        product = create_product(tenant['company'], name='Yogurt', sku='YOG-1', requires_batch=True, min_stock=1)
        create_batch(product, tenant['branch'], initial_quantity=50)

        call_command('send_low_stock_digest', stdout=StringIO())

        self.assertEqual(len(mail.outbox), 0)

    def test_tenant_isolation_across_digests(self):
        tenant_a = create_full_tenant('Abarrotes Don Chuy', 'Centro', 'admin@donchuy.test', role=UserProfile.Role.ADMINISTRADOR)
        tenant_b = create_full_tenant('Papelería La Estrella', 'Norte', 'admin@estrella.test', role=UserProfile.Role.ADMINISTRADOR)
        product_a = create_product(tenant_a['company'], name='Yogurt', sku='YOG-1', requires_batch=True, min_stock=10)
        create_batch(product_a, tenant_a['branch'], initial_quantity=1)
        # tenant_b sin stock bajo: no debe recibir nada, ni mezclar sus
        # productos con el resumen del tenant_a.
        product_b = create_product(tenant_b['company'], name='Resistol', sku='RES-1', requires_batch=True, min_stock=1)
        create_batch(product_b, tenant_b['branch'], initial_quantity=50)

        call_command('send_low_stock_digest', stdout=StringIO())

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['admin@donchuy.test'])
        self.assertIn('Yogurt', mail.outbox[0].body)
        self.assertNotIn('Resistol', mail.outbox[0].body)
