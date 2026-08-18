from django.db import models

from core.managers import TenantScopedManager


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class BaseTenantModel(TimeStampedModel):
    """Modelo base para todo dato que pertenece a un tenant.

    Regla no negociable del proyecto (ver CLAUDE.md #2): cualquier modelo con
    datos de tenant hereda de aquí y se filtra vía `objects.for_user(...)` /
    `for_company(...)` — nunca con un filtro manual repetido en cada ViewSet.

    `company` se define aquí directo (en vez de solo derivarlo de `branch`)
    para que el filtro de aislamiento sea una sola columna indexada, igual
    para todos los modelos, sin importar cuántos FKs intermedios tenga cada
    uno hacia la company.
    """

    company = models.ForeignKey(
        'tenants.Company',
        on_delete=models.CASCADE,
        related_name='%(class)ss',
    )

    objects = TenantScopedManager()

    class Meta:
        abstract = True
        ordering = ['id']
