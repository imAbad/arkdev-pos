from rest_framework.permissions import SAFE_METHODS, BasePermission


class HasCapability(BasePermission):
    """Permission class parametrizable sobre UserProfile.capabilities.

    Patrón reutilizado tal cual de pharma_core (capability JSON + permission
    class DRF, ver decisiones_post_auditoria.md §2) — solo cambia qué
    capabilities existen, no la arquitectura. No usar directo:
    parametrizar con `capability_required(...)`.

    Un usuario sin profile (staff/soporte sin tenant asignado) nunca cumple
    ninguna capability por esta vía — mismo criterio que TenantScopedManager.
    """

    capability = None
    message = 'No tienes la capability requerida para esta acción.'

    def has_permission(self, request, view):
        capability = getattr(view, 'required_capability', None) or self.capability
        if not capability:
            return True

        profile = getattr(request.user, 'profile', None)
        if profile is None:
            return False

        # ADMINISTRADOR pasa cualquier gate de capability sin tener que
        # tenerla marcada explícitamente en su JSON — mismo criterio que
        # ya usaba sales.services.close_shift (is_admin or is_override) y
        # que la especificación pide: ver/operar la caja es visibilidad y
        # autoridad administrativa básica, no algo que dependa de que
        # alguien le haya prendido un flag a mano. Bug real encontrado
        # probando la app a mano: admin@fortuna.test (ADMINISTRADOR,
        # capabilities={}) no podía ni ver el turno actual.
        if profile.role == profile.Role.ADMINISTRADOR:
            return True

        return bool(profile.capabilities.get(capability))


def capability_required(capability):
    """Factory: genera una permission class de DRF atada a una capability.

    Uso: `permission_classes = [IsAuthenticated, capability_required('can_authorize_exceptions')]`
    """
    class_name = 'Has' + ''.join(part.title() for part in capability.split('_')) + 'Capability'
    return type(class_name, (HasCapability,), {'capability': capability})


CanAuthorizeExceptions = capability_required('can_authorize_exceptions')
HandlesCash = capability_required('handles_cash')


class IsAdministrator(BasePermission):
    """Gate por rol, no por capability — para lo que es EXCLUSIVO del
    dueño/gerente (usuarios, precios/costos, configuración de tenant):
    ni siquiera un Supervisor (CAJERO + can_authorize_exceptions) puede
    entrar por aquí. Ver IsAdministratorOrSupervisor para lo que sí
    comparten ambos."""

    message = 'Esta acción requiere el rol de administrador.'

    def has_permission(self, request, view):
        profile = getattr(request.user, 'profile', None)
        return profile is not None and profile.role == profile.Role.ADMINISTRADOR


class IsAdministratorOrReadOnly(BasePermission):
    """Cualquier usuario autenticado del tenant puede LEER (branding y
    feature flags son visibles para todos — AppHeader/AuthProvider los
    cargan sin importar rol, ver company-settings/). Solo ADMINISTRADOR
    puede escribir: son configuración de negocio (nombre, logo, color,
    módulos activos), no operación diaria. Bug real encontrado al
    revisar CompanySettingsViewSet para el punto 3: no tenía NINGÚN
    permission_classes propio, heredaba solo IsAuthenticated del default
    de DRF — cualquier cajero autenticado podía hacer PATCH ahí."""

    message = 'Esta acción requiere el rol de administrador.'

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        profile = getattr(request.user, 'profile', None)
        return profile is not None and profile.role == profile.Role.ADMINISTRADOR


class IsAdministratorOrSupervisor(BasePermission):
    """ADMINISTRADOR o CAJERO con can_authorize_exceptions — 'Supervisor'
    no es un rol propio en este modelo (decisiones_post_auditoria.md §5),
    es este mismo criterio ya usado para el override de cierre de turno
    ajeno (sales.services.close_shift). Reportes, exportación y gestión
    de inventario (no de precio/catálogo) usan este gate: visibilidad y
    autoridad operativa amplia, no exclusiva del dueño."""

    message = 'Esta acción requiere permisos de administrador o supervisor.'

    def has_permission(self, request, view):
        profile = getattr(request.user, 'profile', None)
        if profile is None:
            return False
        return profile.role == profile.Role.ADMINISTRADOR or bool(profile.capabilities.get('can_authorize_exceptions'))
