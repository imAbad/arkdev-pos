from django.conf import settings
from django.db import models

from core.models import BaseTenantModel


class CashRegister(BaseTenantModel):
    """Caja física de una sucursal. Extraído casi sin cambios de pharma_core
    (ver decisiones_post_auditoria.md §2 — ya genérico, sin acoplamiento a
    farmacia)."""

    branch = models.ForeignKey(
        'tenants.Branch',
        on_delete=models.CASCADE,
        related_name='cash_registers',
    )
    name = models.CharField(max_length=50)
    is_active = models.BooleanField(default=True)

    def save(self, *args, **kwargs):
        self.company_id = self.branch.company_id
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.name} ({self.branch.name})'


class CashShift(BaseTenantModel):
    """Turno de caja: apertura -> ventas del turno -> cierre con arqueo ciego.

    El cajero declara `actual_closing_balance`/`actual_voucher_total` SIN ver
    lo que el sistema espera — `expected_*` se calcula server-side en
    `sales.services.close_shift` y solo se conoce después de declarar (ver
    arquitectura_tecnica_pos.md §8: portar la regla de arqueo ciego, no solo
    el modelo). Las diferencias no se guardan como columna, se derivan como
    property — mismo criterio que pharma_core.
    """

    class Status(models.TextChoices):
        OPEN = 'OPEN', 'Abierto'
        CLOSED = 'CLOSED', 'Cerrado'

    cash_register = models.ForeignKey(
        CashRegister,
        on_delete=models.PROTECT,
        related_name='shifts',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='shifts',
    )
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='closed_shifts',
        null=True,
        blank=True,
    )
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    opening_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    expected_closing_balance = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    actual_closing_balance = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    expected_voucher_total = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    actual_voucher_total = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)

    class Meta(BaseTenantModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=['cash_register'],
                condition=models.Q(status='OPEN'),
                name='unique_open_shift_per_register',
            ),
        ]

    def save(self, *args, **kwargs):
        self.company_id = self.cash_register.company_id
        super().save(*args, **kwargs)

    @property
    def cash_difference(self):
        if self.actual_closing_balance is None or self.expected_closing_balance is None:
            return None
        return self.actual_closing_balance - self.expected_closing_balance

    @property
    def voucher_difference(self):
        if self.actual_voucher_total is None or self.expected_voucher_total is None:
            return None
        return self.actual_voucher_total - self.expected_voucher_total

    def __str__(self):
        return f'Turno {self.id} · {self.cash_register.name} · {self.user.email}'


class Sale(BaseTenantModel):
    """Rediseñado desde cero (no extraído) — pago dividido, impuestos reales
    por línea, e idempotencia para offline desde el modelo, aunque la cola
    de sincronización no se construya todavía (arquitectura_tecnica_pos.md
    §4.2 y §9 punto 4; decisión confirmada en la sesión de construcción).

    `branch`/`cash_register` se guardan denormalizados además de
    `cash_shift` (de donde se derivan en save()) — igual que el resto de
    modelos con parent scoping en este proyecto, para poder reportar por
    sucursal/caja sin tener que atravesar el join hasta el turno.

    `client` (FK a customers.Client, para fiado) se agrega en el punto 5 del
    orden de construcción, junto con `customers` — nullable porque la
    mayoría de las ventas no son a crédito. Un Payment con method=CREDIT
    exige `client` (ver sales.services.create_sale); su contabilidad la
    resuelve customers.services.charge_credit.
    """

    class Status(models.TextChoices):
        COMPLETED = 'COMPLETED', 'Completada'
        CANCELLED = 'CANCELLED', 'Cancelada'
        REFUNDED = 'REFUNDED', 'Devuelta'

    branch = models.ForeignKey('tenants.Branch', on_delete=models.PROTECT, related_name='sales')
    cash_register = models.ForeignKey(CashRegister, on_delete=models.PROTECT, related_name='sales')
    cash_shift = models.ForeignKey(CashShift, on_delete=models.PROTECT, related_name='sales')
    client = models.ForeignKey(
        'customers.Client', on_delete=models.PROTECT, related_name='sales', null=True, blank=True,
    )

    # Idempotencia para offline: lo genera el cliente (POS offline), no el
    # servidor — por eso sin default a nivel de modelo (sales.services.
    # create_sale sí genera uno server-side si no llega, para no bloquear
    # el flujo síncrono de hoy mientras la cola de sync no exista).
    client_uuid = models.UUIDField(unique=True)
    # Distinto de created_at (auto_now_add, reloj del servidor): lo declara
    # el cliente — cuándo ocurrió la venta de verdad, no cuándo llegó al
    # servidor (relevante en cuanto exista la cola offline).
    occurred_at = models.DateTimeField()

    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    # Suma de SaleDetail.tax_amount — ver la nota de diseño en SaleDetail
    # sobre por qué el impuesto se calcula y guarda por línea, no solo aquí.
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2)
    total = models.DecimalField(max_digits=12, decimal_places=2)

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.COMPLETED)

    def save(self, *args, **kwargs):
        self.cash_register_id = self.cash_shift.cash_register_id
        self.branch_id = self.cash_shift.cash_register.branch_id
        self.company_id = self.cash_shift.company_id
        super().save(*args, **kwargs)

    def __str__(self):
        return f'Venta {self.id} · {self.total}'


class SaleDetail(BaseTenantModel):
    """`batch` nullable a propósito: FEFO es opcional por producto
    (Product.requires_batch), no obligatorio por línea de venta — cambio
    clave respecto a pharma_core (decisiones_post_auditoria.md §3).

    `tax_amount` se calcula y persiste por línea, no solo a nivel de Sale.
    Decisión tomada en esta sesión: la especificación (§7) exige exenciones
    tipo "alimentos básicos", es decir tasas de IVA distintas dentro de una
    misma venta — sumar impuesto solo al total perdería esa granularidad.
    `tax_rate_applied` congela `Product.tax_rate` al momento de la venta
    (si el producto cambia de tasa después, no reescribe ventas pasadas).
    """

    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='details')
    product = models.ForeignKey('catalog.Product', on_delete=models.PROTECT, related_name='sale_details')
    batch = models.ForeignKey(
        'catalog.Batch', on_delete=models.PROTECT, related_name='sale_details', null=True, blank=True,
    )

    # Decimal desde ahora (no placeholder): KG/LITRO/GRAMO necesitan
    # cantidad fraccionaria real (ej. 0.750 kg) — un IntegerField no
    # alcanzaría y migrar el tipo de columna después es justo lo que
    # arquitectura_tecnica_pos.md §4.3 ya pedía evitar para `image`. 3
    # decimales cubre gramos como unidad mínima de kg/litro; PIEZA/PAQUETE/
    # SERVICIO simplemente usan enteros representados como Decimal (3.000).
    quantity = models.DecimalField(max_digits=10, decimal_places=3)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    tax_rate_applied = models.DecimalField(max_digits=5, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2)

    def save(self, *args, **kwargs):
        self.company_id = self.sale.company_id
        super().save(*args, **kwargs)

    @property
    def subtotal(self):
        return self.quantity * self.unit_price

    def __str__(self):
        return f'{self.product.name} x{self.quantity}'


class Payment(BaseTenantModel):
    """Nuevo — habilita pago dividido (N registros por venta que suman el
    total), no existía en pharma_core."""

    class Method(models.TextChoices):
        CASH = 'CASH', 'Efectivo'
        CARD = 'CARD', 'Tarjeta'
        TRANSFER = 'TRANSFER', 'Transferencia'
        CREDIT = 'CREDIT', 'Crédito (fiado)'

    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='payments')
    method = models.CharField(max_length=10, choices=Method.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    def save(self, *args, **kwargs):
        self.company_id = self.sale.company_id
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.method} {self.amount}'
