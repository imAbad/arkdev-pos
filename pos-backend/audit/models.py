from django.conf import settings
from django.db import models

from core.models import BaseTenantModel


class AuditLog(BaseTenantModel):
    """Bitácora de auditoría — agnóstica de dominio (ver
    decisiones_post_auditoria.md §2: se reutiliza tal cual, sin cambios de
    esquema). Cualquier app puede escribir aquí vía `audit.services.log_action`
    sin que `audit` tenga que conocer sus modelos.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs',
    )
    action = models.CharField(max_length=100)
    model_name = models.CharField(max_length=100, blank=True)
    object_id = models.CharField(max_length=64, blank=True)
    changes = models.JSONField(default=dict, blank=True)

    class Meta(BaseTenantModel.Meta):
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.action} · {self.model_name}:{self.object_id}'
