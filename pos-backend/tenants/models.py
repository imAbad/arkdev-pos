import secrets

from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

from core.models import BaseTenantModel, TimeStampedModel
from tenants.managers import UserManager


class User(AbstractUser):
    """Una cuenta, una contraseña, dos identificadores posibles para
    entrar: `email` y `username`. No son dos mecanismos de auth
    distintos — el login (ver `tenants.serializers.
    IdentifierTokenObtainPairSerializer` / `tenants.services.
    authenticate_by_identifier`) acepta cualquiera de los dos y valida
    contra la MISMA contraseña real de la cuenta.

    `username` original de AbstractUser: removido a propósito. Colisionaba
    entre tenants en pharma_core (ver decisiones_post_auditoria.md #5,
    CLAUDE.md #3) porque era el ÚNICO identificador y único solo por
    tenant. El `username` de abajo es uno nuevo y deliberadamente
    distinto: único A NIVEL SISTEMA (mismo principio que `email`, no por
    tenant, así que no repite ese bug), obligatorio al dar de alta un
    usuario (ver `UserCreateSerializer`).

    `USERNAME_FIELD = 'email'` se mantiene por razones puramente de
    plomería de Django (`createsuperuser`, `ModelBackend`, admin) — NO
    determina qué acepta el login real de la API, que vive en
    `IdentifierTokenObtainPairSerializer` y no pasa por `USERNAME_FIELD`
    en absoluto. Por eso `email` puede ser opcional aquí: una cuenta
    dada de alta solo con `username` sigue pudiendo entrar (por
    username), simplemente no podría entrar por correo porque no tiene.

    Corrección de sesión: una ronda anterior interpretó "login alterno"
    como un SEGUNDO mecanismo de autenticación independiente (username +
    fecha de nacimiento, sin contraseña) — eso era un malentendido y se
    removió por completo (ver `UserProfile.date_of_birth` y el historial
    de `tenants.services`/`tenants.viewsets`/`config.urls` para lo que
    ya no existe). `date_of_birth` se conserva solo como dato de perfil,
    nunca para autenticar.
    """

    # Opcional: una cuenta puede darse de alta solo con username (caso
    # típico de mostrador) y entrar sin nunca haber tenido correo.
    # unique=True + null=True: Postgres no considera NULL igual a NULL,
    # así que múltiples cuentas sin email conviven sin chocar, pero si
    # alguien SÍ tiene uno, es único en todo el sistema (mismo criterio
    # que username, ver abajo).
    email = models.EmailField('email', unique=True, null=True, blank=True)

    # Igual de único a nivel sistema que email (no por tenant — no repite
    # el bug de pharma_core), pero a diferencia de email, obligatorio al
    # dar de alta (ver UserCreateSerializer.username, sin default=False).
    username = models.CharField(max_length=30, unique=True, null=True, blank=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self):
        return self.email or self.username or f'user #{self.pk}'


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
    # Dato de perfil administrativo (ej. verificación de identidad en
    # persona) — NUNCA se usa para autenticar a nadie, no es parte de
    # ningún flujo de login. Null para perfiles que no lo capturaron.
    date_of_birth = models.DateField(null=True, blank=True)

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
