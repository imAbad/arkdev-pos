from datetime import timedelta

from django.conf import settings
from django.contrib.auth import authenticate
from django.utils import timezone

from audit.services import log_action
from tenants.models import SupervisorAuthorization


class AuthorizationError(Exception):
    """Error de regla de negocio al solicitar o consumir una autorización
    de supervisor (-> 403)."""


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
