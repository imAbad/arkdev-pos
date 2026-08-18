"""Consultas de reporte — agregaciones de solo lectura sobre datos que ya
existen (Sale/SaleDetail/Payment, Batch, CashShift). Adaptadas al modelo de
datos de este proyecto, no copiadas de pharma_core: aquí no hay lotes de
medicamento ni caducidad regulada, pero SÍ hay Batch.expiration_date (mismo
campo, otro giro) — se reutiliza para el reporte de mermas por caducidad
(ver expired_stock_report, la única de las cuatro consultas sin
equivalente directo: pharma_core no modela mermas como entidad propia,
tampoco este proyecto — se infiere de stock remanente en lotes ya
caducados, dato que sí existe hoy, sin inventar un modelo nuevo de ajustes
de inventario).

Cada función recibe `company` ya resuelta (el caller la saca del profile
del usuario autenticado) — ninguna de estas consultas vuelve a filtrar por
tenant más allá de eso, ya viene acotado desde aquí.
"""
from datetime import timedelta

from django.db.models import DecimalField, ExpressionWrapper, F, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from catalog.models import Batch
from sales.models import CashShift, Payment, Sale, SaleDetail


def sales_by_product(*, company, date_from, date_to, branch=None, cashier=None, group_by='product'):
    """`group_by='product'` -> una fila por producto (con su categoría como
    columna de contexto). `group_by='category'` -> una fila por categoría.
    `group_by='cashier'` -> una fila por cajero (punto 2: "ventas por
    cajero" ya estaba en la especificación original §8 — la trazabilidad
    de quién vendió no requirió ningún campo nuevo, `Sale.cash_shift.user`
    ya existía desde que CashShift existe; esto solo lo expone). `cashier`
    (aparte de group_by) filtra cualquiera de los tres modos a lo que
    vendió un cajero específico, sin cambiar cómo se agrupan las filas.

    `revenue` se calcula como `Sum(quantity * unit_price)`, no
    `Sum('subtotal')` — `SaleDetail.subtotal` es una `@property` de Python
    (quantity * unit_price), no una columna real, el ORM no puede agregar
    sobre ella directo."""
    revenue_expr = ExpressionWrapper(
        F('quantity') * F('unit_price'), output_field=DecimalField(max_digits=14, decimal_places=2),
    )
    qs = SaleDetail.objects.filter(
        company=company,
        sale__status=Sale.Status.COMPLETED,
        sale__occurred_at__date__gte=date_from,
        sale__occurred_at__date__lte=date_to,
    )
    if branch is not None:
        qs = qs.filter(sale__branch=branch)
    if cashier is not None:
        qs = qs.filter(sale__cash_shift__user=cashier)

    if group_by == 'category':
        qs = qs.values('product__category__id', 'product__category__name')
        qs = qs.annotate(
            category_id=F('product__category__id'),
            category_name=Coalesce(F('product__category__name'), Value('Sin categoría')),
            quantity_sold=Sum('quantity'),
            revenue=Sum(revenue_expr),
            tax=Sum('tax_amount'),
        ).values('category_id', 'category_name', 'quantity_sold', 'revenue', 'tax')
    elif group_by == 'cashier':
        qs = qs.values('sale__cash_shift__user__id', 'sale__cash_shift__user__email')
        qs = qs.annotate(
            cashier_id=F('sale__cash_shift__user__id'),
            cashier_email=F('sale__cash_shift__user__email'),
            quantity_sold=Sum('quantity'),
            revenue=Sum(revenue_expr),
            tax=Sum('tax_amount'),
        ).values('cashier_id', 'cashier_email', 'quantity_sold', 'revenue', 'tax')
    else:
        qs = qs.values('product__id', 'product__name', 'product__category__name')
        qs = qs.annotate(
            product_id=F('product__id'),
            product_name=F('product__name'),
            category_name=Coalesce(F('product__category__name'), Value('Sin categoría')),
            quantity_sold=Sum('quantity'),
            revenue=Sum(revenue_expr),
            tax=Sum('tax_amount'),
        ).values('product_id', 'product_name', 'category_name', 'quantity_sold', 'revenue', 'tax')

    return list(qs.order_by('-revenue'))


def inventory_valuation(*, company, branch=None):
    """Stock remanente (lotes no caducados, current_quantity > 0) valuado a
    costo — no a precio de venta, es el valor de lo que hay en existencia,
    no lo que se cobraría por venderlo."""
    qs = Batch.objects.filter(company=company, current_quantity__gt=0, expiration_date__gte=timezone.localdate())
    if branch is not None:
        qs = qs.filter(branch=branch)

    valuation_expr = ExpressionWrapper(
        F('current_quantity') * F('product__cost_price'), output_field=DecimalField(max_digits=14, decimal_places=2),
    )
    qs = qs.values('product__id', 'product__name', 'product__category__name')
    qs = qs.annotate(
        product_id=F('product__id'),
        product_name=F('product__name'),
        category_name=Coalesce(F('product__category__name'), Value('Sin categoría')),
        quantity=Sum('current_quantity'),
        valuation=Sum(valuation_expr),
    ).values('product_id', 'product_name', 'category_name', 'quantity', 'valuation')

    return list(qs.order_by('-valuation'))


def expired_stock_report(*, company, branch=None):
    """Mermas por caducidad: lotes ya vencidos que todavía tienen stock sin
    vender — nadie los movió a un ajuste de inventario porque ese concepto
    no existe todavía en el modelo (ver docstring del módulo). Una fila por
    lote, no agregado por producto, porque cada lote caduca en su propia
    fecha y eso es justo lo que un administrador necesita ver para decidir
    qué dar de baja."""
    qs = Batch.objects.filter(company=company, current_quantity__gt=0, expiration_date__lt=timezone.localdate())
    if branch is not None:
        qs = qs.filter(branch=branch)

    qs = qs.select_related('product', 'branch').order_by('expiration_date')

    rows = []
    for batch in qs:
        valuation = batch.current_quantity * batch.product.cost_price
        rows.append({
            'batch_id': batch.id,
            'batch_number': batch.batch_number,
            'product_id': batch.product_id,
            'product_name': batch.product.name,
            'branch_id': batch.branch_id,
            'branch_name': batch.branch.name,
            'expiration_date': batch.expiration_date,
            'quantity': batch.current_quantity,
            'valuation': valuation,
        })
    return rows


def near_expiry_stock_report(*, company, days=7, branch=None):
    """Punto 4: visibilidad de lo que está por caducar (todavía vigente,
    no vencido — eso es expired_stock_report) para que un administrador
    decida promoción antes de que se convierta en merma. `days` es la
    ventana desde hoy (inclusive), configurable — 7 por default. No
    incluye lotes ya caducados (esos van en expired_stock_report, no se
    duplica aquí) ni lotes sin stock."""
    today = timezone.localdate()
    limit = today + timedelta(days=days)
    qs = Batch.objects.filter(
        company=company, current_quantity__gt=0, expiration_date__gte=today, expiration_date__lte=limit,
    )
    if branch is not None:
        qs = qs.filter(branch=branch)

    qs = qs.select_related('product', 'branch').order_by('expiration_date')

    rows = []
    for batch in qs:
        valuation = batch.current_quantity * batch.product.cost_price
        rows.append({
            'batch_id': batch.id,
            'batch_number': batch.batch_number,
            'product_id': batch.product_id,
            'product_name': batch.product.name,
            'branch_id': batch.branch_id,
            'branch_name': batch.branch.name,
            'expiration_date': batch.expiration_date,
            'days_to_expire': (batch.expiration_date - today).days,
            'quantity': batch.current_quantity,
            'valuation': valuation,
        })
    return rows


def cash_shift_closures(*, company, date_from, date_to, branch=None):
    """El reporte que conecta directo con el arqueo ciego (CloseShiftScreen,
    punto 4): un renglón por turno cerrado en el rango, con la diferencia
    ya calculada por el modelo (cash_difference/voucher_difference), no
    recalculada aquí — una sola fuente de verdad para ese número."""
    qs = CashShift.objects.filter(
        company=company,
        status=CashShift.Status.CLOSED,
        closed_at__date__gte=date_from,
        closed_at__date__lte=date_to,
    )
    if branch is not None:
        qs = qs.filter(cash_register__branch=branch)

    qs = qs.select_related('cash_register', 'cash_register__branch', 'user').order_by('-closed_at')

    rows = []
    for shift in qs:
        rows.append({
            'id': shift.id,
            'branch_name': shift.cash_register.branch.name,
            'register_name': shift.cash_register.name,
            'user_email': shift.user.email,
            'opened_at': shift.opened_at,
            'closed_at': shift.closed_at,
            'opening_balance': shift.opening_balance,
            'expected_closing_balance': shift.expected_closing_balance,
            'actual_closing_balance': shift.actual_closing_balance,
            'cash_difference': shift.cash_difference,
            'expected_voucher_total': shift.expected_voucher_total,
            'actual_voucher_total': shift.actual_voucher_total,
            'voucher_difference': shift.voucher_difference,
        })
    return rows


def sales_summary_by_payment_method(*, company, date_from, date_to, branch=None):
    """Desglose por forma de pago del mismo rango — apoyo directo del
    reporte de corte de caja (pos_especificacion_funcional.md §7: 'debe
    desglosar por forma de pago'), reutiliza el mismo filtro de fecha/
    sucursal que sales_by_product."""
    qs = Payment.objects.filter(
        company=company,
        sale__status=Sale.Status.COMPLETED,
        sale__occurred_at__date__gte=date_from,
        sale__occurred_at__date__lte=date_to,
    )
    if branch is not None:
        qs = qs.filter(sale__branch=branch)

    qs = qs.values('method').annotate(total=Sum('amount')).order_by('-total')
    return list(qs)
