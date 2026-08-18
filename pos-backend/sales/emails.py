"""Punto 6: ticket de venta por correo — mismo detalle que Ticket.tsx
(productos, cantidades, precios, IVA, total, pagos, fecha, nombre del
negocio), texto plano simple, no HTML ni PDF (explícitamente fuera de
alcance para esta ronda). Separado de sales/services.py a propósito: eso
es lógica de negocio de venta, esto es un side-effect de I/O externo
(SMTP) con su propio tipo de error.
"""
from decimal import ROUND_HALF_UP, Decimal

from django.core.mail import EmailMultiAlternatives

from sales.models import Payment

_METHOD_LABELS = {
    Payment.Method.CASH: 'Efectivo',
    Payment.Method.CARD: 'Tarjeta',
    Payment.Method.TRANSFER: 'Transferencia',
    Payment.Method.CREDIT: 'Crédito (fiado)',
}

_CENTS = Decimal('0.01')


def _money(value):
    # SaleDetail.subtotal es `quantity * unit_price` (una @property, no
    # columna): quantity trae 3 decimales, así que sin esto el correo
    # mostraba "24.00000" en vez de "24.00" — nunca crudo, siempre a
    # centavos, igual que formatCurrency() ya hace en Ticket.tsx.
    return Decimal(value).quantize(_CENTS, rounding=ROUND_HALF_UP)


class TicketEmailError(Exception):
    """El envío falló (SMTP no configurado, credenciales inválidas, host
    inalcanzable, etc.) -> el caller lo traduce a un mensaje humano, nunca
    un 500 con el traceback de smtplib crudo."""


def send_sale_ticket_email(*, sale, business_name, to_email, change_given=None):
    lines = [
        business_name,
        'Ticket de venta',
        f'Fecha: {sale.occurred_at:%d/%m/%Y %H:%M}',
        '',
    ]
    for detail in sale.details.select_related('product').all():
        lines.append(
            f'{detail.product.name} — {detail.quantity} x {_money(detail.unit_price)} = {_money(detail.subtotal)}',
        )

    lines += [
        '',
        f'Subtotal: {_money(sale.subtotal)}',
        f'IVA: {_money(sale.tax_amount)}',
        f'Total: {_money(sale.total)}',
        '',
        'Pago:',
    ]
    for payment in sale.payments.all():
        label = _METHOD_LABELS.get(payment.method, payment.method)
        lines.append(f'{label}: {_money(payment.amount)}')
    if change_given:
        lines.append(f'Cambio entregado: {_money(change_given)}')

    body = '\n'.join(lines)

    try:
        message = EmailMultiAlternatives(
            subject=f'Tu ticket de compra — {business_name}',
            body=body,
            to=[to_email],
        )
        message.send(fail_silently=False)
    except Exception as exc:
        # Amplio a propósito: smtplib puede fallar de muchas formas
        # distintas (auth, conexión, timeout) y ninguna debe llegar cruda
        # al cliente — es justo la frontera externa que el punto 5 ya
        # identificó como el único lugar donde un catch amplio es correcto.
        raise TicketEmailError(
            'No se pudo enviar el correo. Verifica la dirección o intenta de nuevo más tarde.',
        ) from exc
