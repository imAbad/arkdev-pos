class TenantScopedViewSetMixin:
    """Filtra automáticamente el queryset de un ViewSet por la company del
    usuario autenticado, y fuerza esa company al crear.

    Este mixin es EL único lugar donde un ViewSet toca el filtro de tenant.
    Ningún ViewSet debe sobreescribir get_queryset() con su propio filtro
    manual (ver documentacion/arquitectura_tecnica_pos.md, sección 5).
    """

    def get_queryset(self):
        return self.queryset.model.objects.for_user(self.request.user)

    def perform_create(self, serializer):
        profile = self.request.user.profile
        serializer.save(company=profile.company)
