from datetime import timedelta

from django.conf import settings
from django.contrib.auth import authenticate
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from audit.services import log_action
from tenants.models import SupervisorAuthorization, User, UserProfile


class AuthorizationError(Exception):
    """Error de regla de negocio al solicitar o consumir una autorización
    de supervisor (-> 403)."""


def authenticate_by_identifier(*, identifier, password):
    """Resuelve la cuenta por `username` O `email` — son dos
    identificadores de la MISMA cuenta, no dos mecanismos de auth
    distintos, así que ambos validan contra la MISMA contraseña real
    (ver IdentifierTokenObtainPairSerializer, que reemplaza el
    TokenObtainPairSerializer estándar de SimpleJWT para aceptar
    cualquiera de los dos en vez de solo `USERNAME_FIELD`).

    Devuelve el User si las credenciales son válidas y la cuenta está
    activa, None en cualquier otro caso (identificador inexistente,
    password incorrecto, cuenta inactiva) — sin distinguir el motivo en
    la respuesta pública, mismo criterio que el login por email de
    siempre nunca reveló si el problema era el correo o el password.
    """
    if not identifier:
        return None
    user = User.objects.filter(Q(email__iexact=identifier) | Q(username__iexact=identifier)).first()
    if user is None or not user.is_active or not user.check_password(password):
        return None
    return user


class UserManagementError(Exception):
    """Error de regla de negocio al crear/desactivar un usuario del tenant
    (-> 400)."""


def create_tenant_user(*, username, password, branch, role, email=None, capabilities=None, actor=None, date_of_birth=None):
    """Crea el `User` (login) y su `UserProfile` (branch/role/capabilities)
    en una sola transacción — no tiene sentido que exista el uno sin el
    otro (ver UserProfile.save(): company se deriva de branch, así que
    basta con pasar un branch ya acotado al tenant del actor -mismo
    criterio anti-IDOR que reports._resolve_branch, aplicado vía
    TenantScopedFieldsMixin en el serializer-).

    `username` es el único identificador obligatorio (ver
    UserCreateSerializer) — `email` es opcional: una cuenta dada de alta
    sin correo sigue pudiendo entrar por username, simplemente no por
    correo. `date_of_birth` es un dato de perfil administrativo, sin
    relación con el login (ver UserProfile.date_of_birth)."""
    with transaction.atomic():
        user = User.objects.create_user(email=email, password=password, username=username)
        profile = UserProfile.objects.create(
            user=user, branch=branch, role=role, capabilities=capabilities or {}, date_of_birth=date_of_birth,
        )
    log_action(
        company=profile.company, user=actor, action='user_management.created',
        instance=profile, changes={'username': username, 'email': email, 'role': role},
    )
    return profile


def deactivate_user(*, target_profile, actor=None):
    """Desactiva el login del usuario (`User.is_active=False` — SimpleJWT
    rechaza tokens de un usuario inactivo en su próxima verificación, ver
    JWTAuthentication.get_user()). Nunca un DELETE: el historial de ventas/
    turnos/auditoría sigue apuntando a este usuario, borrarlo rompería esas
    referencias o las dejaría huérfanas.

    Salvaguarda real (punto 9, el de mayor riesgo de esta ronda): si
    `target_profile` es el ÚLTIMO ADMINISTRADOR activo del tenant, se
    rechaza — sin importar quién lo intente, no solo si es el propio
    admin desactivándose a sí mismo. Dejar un tenant sin ningún
    administrador activo es un lockout total (nadie puede volver a dar de
    alta/reactivar a nadie), así que la regla protege el riesgo real, no
    solo el caso literal de auto-desactivación.
    """
    if target_profile.role == UserProfile.Role.ADMINISTRADOR:
        other_active_admins_exist = (
            UserProfile.objects.filter(
                company=target_profile.company, role=UserProfile.Role.ADMINISTRADOR, user__is_active=True,
            )
            .exclude(pk=target_profile.pk)
            .exists()
        )
        if not other_active_admins_exist:
            raise UserManagementError('No puedes desactivar al último administrador activo del negocio.')

    target_profile.user.is_active = False
    target_profile.user.save(update_fields=['is_active'])
    log_action(
        company=target_profile.company, user=actor, action='user_management.deactivated',
        instance=target_profile, changes={'email': target_profile.user.email},
    )


def reactivate_user(*, target_profile, actor=None):
    target_profile.user.is_active = True
    target_profile.user.save(update_fields=['is_active'])
    log_action(
        company=target_profile.company, user=actor, action='user_management.reactivated',
        instance=target_profile, changes={'email': target_profile.user.email},
    )


def request_supervisor_authorization(*, requesting_user, email, password, reason=''):
    """Valida credenciales de un supervisor (`ADMINISTRADOR` o
    `capabilities.can_authorize_exceptions`) del MISMO tenant que
    `requesting_user`, sin tocar la sesión de `requesting_user`, y emite un
    token corto de un solo uso si todo es válido.

    Cada intento —éxito o fallo— queda en `AuditLog` (pos_especificacion_
    funcional.md §13: "log de acciones sensibles... quién, cuándo, qué").
    """
    requesting_profile = getattr(requesting_user, 'profile', None)
    if requesting_profile is None:
        raise AuthorizationError('Tu usuario no tiene un perfil de tenant asociado.')

    def _deny(reason_code):
        log_action(
            company=requesting_profile.company,
            user=requesting_user,
            action='supervisor_authorization.denied',
            changes={'reason_code': reason_code, 'email': email, 'requested_reason': reason},
        )
        raise AuthorizationError('Credenciales de supervisor inválidas o sin autoridad para autorizar.')

    supervisor = authenticate(email=email, password=password)
    if supervisor is None:
        _deny('invalid_credentials')

    supervisor_profile = getattr(supervisor, 'profile', None)
    if supervisor_profile is None or supervisor_profile.company_id != requesting_profile.company_id:
        _deny('cross_tenant_or_no_profile')

    is_admin = supervisor_profile.role == supervisor_profile.Role.ADMINISTRADOR
    if not (is_admin or supervisor_profile.can_authorize_exceptions):
        _deny('insufficient_capability')

    authorization = SupervisorAuthorization.objects.create(
        supervisor=supervisor,
        requested_by=requesting_user,
        reason=reason,
        expires_at=timezone.now() + timedelta(minutes=settings.SUPERVISOR_AUTHORIZATION_TTL_MINUTES),
    )

    log_action(
        company=requesting_profile.company,
        user=supervisor,
        action='supervisor_authorization.granted',
        instance=authorization,
        changes={'requested_by': requesting_user.email, 'reason': reason},
    )

    return authorization


def consume_supervisor_authorization(*, token, consuming_user):
    """Consume (de un solo uso) un token emitido por
    `request_supervisor_authorization`. La llama el endpoint de la acción
    sensible real (descuento, cancelación, devolución) cuando exista —
    todavía no hay ninguno construido, esto es el mecanismo genérico.
    """
    try:
        authorization = SupervisorAuthorization.objects.get(token=token)
    except SupervisorAuthorization.DoesNotExist:
        raise AuthorizationError('Token de autorización inválido.')

    if authorization.requested_by_id != consuming_user.id:
        # No solo tenant: el token es del cajero que lo pidió, no
        # transferible a otra sesión aunque sea del mismo tenant.
        raise AuthorizationError('Este token no fue solicitado por tu usuario.')
    if authorization.is_used:
        raise AuthorizationError('Este token ya fue utilizado.')
    if authorization.is_expired:
        raise AuthorizationError('Este token expiró.')

    authorization.used_at = timezone.now()
    authorization.save(update_fields=['used_at'])

    log_action(
        company=authorization.company,
        user=consuming_user,
        action='supervisor_authorization.consumed',
        instance=authorization,
        changes={'supervisor': authorization.supervisor.email, 'reason': authorization.reason},
    )

    return authorization
