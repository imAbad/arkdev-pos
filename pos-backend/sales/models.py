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
