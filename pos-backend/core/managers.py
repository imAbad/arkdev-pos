from django.db import models


class TenantScopedQuerySet(models.QuerySet):
    """QuerySet que sabe filtrarse por tenant (Company).

    Es el único punto donde vive la lógica de aislamiento — todo modelo con
    datos de tenant hereda de core.models.BaseTenantModel y usa este manager,
    en vez de que cada ViewSet reimplemente su propio filtro manual.
    """

    def for_company(self, company):
        if company is None:
            return self.none()
        return self.filter(company=company)

    def for_user(self, user):
        """Filtra por la company del UserProfile del usuario autenticado.

        Un usuario sin profile (p. ej. superusuario de staff sin tenant)
        no ve nada por este camino — el acceso de soporte/staff es una
        decisión aparte (ver SupportAccessLog, pendiente en la arquitectura).
        """
        profile = getattr(user, 'profile', None)
        company = getattr(profile, 'company', None)
        return self.for_company(company)


class TenantScopedManager(models.Manager.from_queryset(TenantScopedQuerySet)):
    pass
