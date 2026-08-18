"""Punto 6: ticket de venta por correo — mismo estándar que el resto
(servicio directo Y API real), más el caso de error humano cuando el
envío falla (nunca un 500 crudo con el traceback de smtplib)."""
from decimal import Decimal
from unittest.mock import patch

from django.core import mail
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from sales.emails import TicketEmailError, send_sale_ticket_email
from sales.tests.factories import create_checkout_context, make_sale


class SendSaleTicketEmailServiceTests(TestCase):
    def setUp(self):
        self.ctx = create_checkout_context(tax_rate=Decimal('16'))
        self.sale = make_sale(self.ctx['shift'], self.ctx['product'], quantity=Decimal('2'), unit_price=Decimal('10.00'))

    def test_sends_an_email_with_the_ticket_detail(self):
        send_sale_ticket_email(sale=self.sale, business_name='Abarrotes Don Chuy', to_email='cliente@test.com')

        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertEqual(sent.to, ['cliente@test.com'])
        self.assertIn('Abarrotes Don Chuy', sent.body)
        self.assertIn(self.ctx['product'].name, sent.body)
        self.assertIn(str(self.sale.total), sent.body)

    def test_line_subtotal_is_rounded_to_cents_not_raw_decimal_precision(self):
        # SaleDetail.subtotal es quantity(3 decimales) * unit_price(2
        # decimales) = una @property con 5 decimales crudos — sin
        # redondear, el correo mostraba "24.00000" en vez de "24.00".
        sale = make_sale(self.ctx['shift'], self.ctx['product'], quantity=Decimal('1.000'), unit_price=Decimal('24.00'))
        send_sale_ticket_email(sale=sale, business_name='Abarrotes Don Chuy', to_email='cliente@test.com')
        body = mail.outbox[-1].body
        self.assertIn('= 24.00', body)
        self.assertNotIn('24.00000', body)

    def test_includes_change_given_when_provided(self):
        send_sale_ticket_email(
            sale=self.sale, business_name='Abarrotes Don Chuy', to_email='cliente@test.com',
            change_given=Decimal('5.00'),
        )
        self.assertIn('Cambio entregado: 5.00', mail.outbox[0].body)

    def test_omits_change_given_when_not_provided(self):
        send_sale_ticket_email(sale=self.sale, business_name='Abarrotes Don Chuy', to_email='cliente@test.com')
        self.assertNotIn('Cambio entregado', mail.outbox[0].body)

    def test_raises_human_error_when_smtp_fails(self):
        with patch('django.core.mail.message.EmailMessage.send', side_effect=OSError('conexión rechazada')):
            with self.assertRaises(TicketEmailError):
                send_sale_ticket_email(sale=self.sale, business_name='Abarrotes Don Chuy', to_email='cliente@test.com')
        self.assertEqual(len(mail.outbox), 0)


class SendTicketEmailApiTests(APITestCase):
    def setUp(self):
        self.ctx_a = create_checkout_context('Abarrotes Don Chuy', 'Centro', 'a@donchuy.test', tax_rate=Decimal('16'))
        self.ctx_b = create_checkout_context('Papelería La Estrella', 'Norte', 'b@estrella.test')
        self.sale = make_sale(self.ctx_a['shift'], self.ctx_a['product'], quantity=Decimal('1'), unit_price=Decimal('20.00'))

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def test_send_ticket_email_success(self):
        self._auth(self.ctx_a['user'])
        response = self.client.post(
            f'/api/v1/sales/{self.sale.id}/send-ticket-email/', {'email': 'cliente@test.com'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['cliente@test.com'])

    def test_rejects_invalid_email_format(self):
        self._auth(self.ctx_a['user'])
        response = self.client.post(
            f'/api/v1/sales/{self.sale.id}/send-ticket-email/', {'email': 'no-es-un-correo'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(len(mail.outbox), 0)

    def test_smtp_failure_returns_clean_error_not_a_raw_500(self):
        self._auth(self.ctx_a['user'])
        with patch('sales.viewsets.send_sale_ticket_email', side_effect=TicketEmailError('No se pudo enviar el correo.')):
            response = self.client.post(
                f'/api/v1/sales/{self.sale.id}/send-ticket-email/', {'email': 'cliente@test.com'}, format='json',
            )
        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertEqual(response.data['detail'], 'No se pudo enviar el correo.')

    def test_cannot_send_ticket_for_another_tenants_sale(self):
        self._auth(self.ctx_b['user'])
        response = self.client.post(
            f'/api/v1/sales/{self.sale.id}/send-ticket-email/', {'email': 'cliente@test.com'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(len(mail.outbox), 0)
