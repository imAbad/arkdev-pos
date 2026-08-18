"""Punto 7: resumen diario de stock bajo — mismo patrón que
sales/emails.py (texto plano, EmailMultiAlternatives, error de I/O
externo separado de la lógica de negocio). El caller (management command)
decide a quién y cuándo; esto solo arma y manda el correo.
"""
from django.core.mail import EmailMultiAlternatives


class LowStockDigestEmailError(Exception):
    """El envío falló (SMTP no configurado, credenciales inválidas, host
    inalcanzable, etc.) -> el caller decide cómo reportarlo (el comando de
    consola, no un request HTTP, así que aquí no hay traducción a mensaje
    humano: eso ya lo hace TicketEmailError en el flujo con usuario)."""


def send_low_stock_digest_email(*, business_name, to_email, rows):
    lines = [
        business_name,
        'Resumen diario de stock bajo',
        '',
        f'{len(rows)} producto(s) en o por debajo de su stock mínimo:',
        '',
    ]
    for row in rows:
        lines.append(f"{row['product_name']} (SKU {row['sku']}) — stock actual: {row['current_stock']}, mínimo: {row['min_stock']}")

    body = '\n'.join(lines)

    try:
        message = EmailMultiAlternatives(
            subject=f'Stock bajo — {business_name}',
            body=body,
            to=[to_email],
        )
        message.send(fail_silently=False)
    except Exception as exc:
        raise LowStockDigestEmailError(f'No se pudo enviar el resumen de stock bajo a {to_email}.') from exc
