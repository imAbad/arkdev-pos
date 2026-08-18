from rest_framework.permissions import BasePermission


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

        return bool(profile.capabilities.get(capability))


def capability_required(capability):
    """Factory: genera una permission class de DRF atada a una capability.

    Uso: `permission_classes = [IsAuthenticated, capability_required('can_authorize_exceptions')]`
    """
    class_name = 'Has' + ''.join(part.title() for part in capability.split('_')) + 'Capability'
    return type(class_name, (HasCapability,), {'capability': capability})


CanAuthorizeExceptions = capability_required('can_authorize_exceptions')
HandlesCash = capability_required('handles_cash')
