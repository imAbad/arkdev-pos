from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
    """Estandariza toda respuesta de error de la API a {"code": ..., "detail": ...}.

    DRF por default no tiene una forma consistente entre ValidationError,
    PermissionDenied, NotFound, etc. — se estandariza desde el día 1
    (ver arquitectura_tecnica_pos.md, sección 6).
    """
    response = exception_handler(exc, context)
    if response is None:
        return None

    response.data = {
        'code': exc.__class__.__name__,
        'detail': response.data,
    }
    return response
