import secrets

from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

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


def company_logo_upload_path(instance, filename):
    # Mismo criterio que catalog.Product.image: prefijo por tenant, listo
    # para Azure Blob vía django-storages aunque hoy no esté activo (ver
    # arquitectura_tecnica_pos.md §4.3).
    return f'tenant_{instance.company_id}/branding/{filename}'


class CompanySettings(BaseTenantModel):
    """Feature flags por tenant — patrón confirmado y reutilizado tal cual
    de pharma_core (ver decisiones_post_auditoria.md #2). También la
    personalización visual mínima del tenant (punto 7, arranque de
    frontend): nombre a mostrar, logo, color de marca."""

    company = models.OneToOneField(
        'tenants.Company',
        on_delete=models.CASCADE,
        related_name='settings',
    )
    enabled_modules = models.JSONField(default=dict, blank=True)

    # business_name puede diferir de Company.name (nombre legal/de
    # registro) — este es el nombre que ve el cliente en la interfaz.
    business_name = models.CharField(max_length=200, blank=True)
    logo = models.ImageField(upload_to=company_logo_upload_path, null=True, blank=True)
    accent_color = models.CharField(
        max_length=7,
        default='#1E5B94',
        validators=[RegexValidator(r'^#[0-9A-Fa-f]{6}$', 'Debe ser un color hex de 6 dígitos, ej. #1E5B94.')],
    )

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


class SupervisorAuthorization(BaseTenantModel):
    """PIN/reautenticación para `can_authorize_exceptions` (punto 6 del
    orden de construcción — pos_especificacion_funcional.md §2/§13):
    descuentos fuera de política, cancelaciones, devoluciones.

    Mecanismo elegido: endpoint separado que valida credenciales del
    supervisor (email+password, mismo mecanismo de auth que ya existe) SIN
    tocar la sesión del cajero actual, y emite un token corto de un solo
    uso. `tenants.services.request_supervisor_authorization` lo emite;
    `consume_supervisor_authorization` lo consume. `sales.services.
    cancel_sale` (punto 10) es el primer consumidor real de esta pieza
    genérica de autorización — cancelar/devolver una venta ya cobrada
    exige un token de este mecanismo, sin excepción de rol.
    """

    token = models.CharField(max_length=64, unique=True, editable=False)
    supervisor = models.ForeignKey(
        'tenants.User', on_delete=models.PROTECT, related_name='granted_authorizations',
    )
    requested_by = models.ForeignKey(
        'tenants.User', on_delete=models.PROTECT, related_name='requested_authorizations',
    )
    reason = models.CharField(max_length=200, blank=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_urlsafe(32)
        if not self.company_id:
            self.company_id = self.requested_by.profile.company_id
        super().save(*args, **kwargs)

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at

    @property
    def is_used(self):
        return self.used_at is not None

    def __str__(self):
        return f'Autorización {self.supervisor.email} -> {self.requested_by.email}'
