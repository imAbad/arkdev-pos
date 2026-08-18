from django.contrib.auth.models import AbstractUser
from django.db import models

from core.models import BaseTenantModel, TimeStampedModel
from tenants.managers import UserManager


class User(AbstractUser):
    """Usuario con login por email — no username (CLAUDE.md #3).

    `username` global colisionaba entre tenants en pharma_core (ver
    decisiones_post_auditoria.md #5). Se elimina y se usa `email`, que ya
    es naturalmente único a nivel de todo el sistema.
    """

    username = None
    email = models.EmailField('email', unique=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self):
        return self.email


class Company(TimeStampedModel):
    """El tenant. Raíz de la jerarquía Company -> Branch -> CashRegister."""

    name = models.CharField(max_length=200)
    tax_id = models.CharField('RFC', max_length=13, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = 'companies'

    def __str__(self):
        return self.name


class Branch(BaseTenantModel):
    name = models.CharField(max_length=200)
    address = models.CharField(max_length=300, blank=True)

    def __str__(self):
        return f'{self.name} ({self.company.name})'


class CompanySettings(BaseTenantModel):
    """Feature flags por tenant — patrón confirmado y reutilizado tal cual
    de pharma_core (ver decisiones_post_auditoria.md #2)."""

    company = models.OneToOneField(
        'tenants.Company',
        on_delete=models.CASCADE,
        related_name='settings',
    )
    enabled_modules = models.JSONField(default=dict, blank=True)

    class Meta(BaseTenantModel.Meta):
        verbose_name_plural = 'company settings'

    def __str__(self):
        return f'Settings de {self.company.name}'


class UserProfile(BaseTenantModel):
    class Role(models.TextChoices):
        CAJERO = 'CAJERO', 'Cajero'
        ADMINISTRADOR = 'ADMINISTRADOR', 'Administrador'

    user = models.OneToOneField(
        'tenants.User',
        on_delete=models.CASCADE,
        related_name='profile',
    )
    branch = models.ForeignKey(
        'tenants.Branch',
        on_delete=models.CASCADE,
        related_name='user_profiles',
    )
    role = models.CharField(max_length=20, choices=Role.choices)
    capabilities = models.JSONField(default=dict, blank=True)

    def save(self, *args, **kwargs):
        # company se deriva de branch para no depender de que quien crea el
        # profile la pase (y no pueda desalinearse de branch.company).
        self.company_id = self.branch.company_id
        super().save(*args, **kwargs)

    @property
    def handles_cash(self):
        return bool(self.capabilities.get('handles_cash'))

    @property
    def can_authorize_exceptions(self):
        return bool(self.capabilities.get('can_authorize_exceptions'))

    def __str__(self):
        return f'{self.user.email} @ {self.branch.name}'
