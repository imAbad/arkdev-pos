from audit.models import AuditLog


def log_action(*, company, action, user=None, instance=None, changes=None):
    """Registra una entrada de auditoría.

    Es la única forma soportada de escribir en AuditLog — otras apps
    (sales, catalog, ...) llaman esto desde su propio services.py en vez de
    crear AuditLog directamente, para no acoplar el resto del sistema al
    esquema exacto de la bitácora.
    """
    model_name = ''
    object_id = ''
    if instance is not None:
        model_name = f'{instance._meta.app_label}.{instance._meta.object_name}'
        object_id = str(instance.pk)

    return AuditLog.objects.create(
        company=company,
        user=user,
        action=action,
        model_name=model_name,
        object_id=object_id,
        changes=changes or {},
    )
