from django.db import models

from core.models import BaseTenantModel


class Client(BaseTenantModel):
    """100% nuevo (decisiones_post_auditoria.md §4 — cero de esto existía en
    pharma_core). Escalado por `company`, no por `branch`: un cliente puede
    comprar fiado en cualquier sucursal del tenant y su cuenta de crédito es
    una sola, no una por sucursal (la tabla de la arquitectura solo dice
    "branch/company FK" sin ser más específica — esta es la interpretación
    tomada, documentada aquí).
    """

    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=20, blank=True)
    # Punto 6: si el cliente de una venta a crédito ya tiene correo
    # guardado, se precarga como sugerencia editable al enviar el ticket
    # — no se exige de antemano, la mayoría de las ventas no tienen
    # Client asociado (solo fiado lo requiere).
    email = models.EmailField(blank=True)
    credit_limit = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)
        if is_new:
            # Toda Client tiene su CreditAccount desde que se crea — no se
            # expone como paso aparte, evita clientes "a medias" sin cuenta.
            CreditAccount.objects.create(company_id=self.company_id, client=self)

    def __str__(self):
        return self.name


class CreditAccount(BaseTenantModel):
    client = models.OneToOneField(Client, on_delete=models.CASCADE, related_name='credit_account')
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def save(self, *args, **kwargs):
        self.company_id = self.client.company_id
        super().save(*args, **kwargs)

    def __str__(self):
        return f'Cuenta de {self.client.name} · saldo {self.balance}'


class CreditMovement(BaseTenantModel):
    """`sale` nullable a propósito (arquitectura_tecnica_pos.md §4.4): un
    ABONO casi siempre no viene de una venta — es el cliente pagando su
    saldo, no comprando algo nuevo."""

    class Type(models.TextChoices):
        CARGO = 'CARGO', 'Cargo'
        ABONO = 'ABONO', 'Abono'

    account = models.ForeignKey(CreditAccount, on_delete=models.CASCADE, related_name='movements')
    sale = models.ForeignKey(
        'sales.Sale', on_delete=models.PROTECT, related_name='credit_movements', null=True, blank=True,
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    type = models.CharField(max_length=10, choices=Type.choices)

    class Meta(BaseTenantModel.Meta):
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        self.company_id = self.account.company_id
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.type} {self.amount} · {self.account.client.name}'
