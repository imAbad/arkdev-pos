class TenantScopedFieldsMixin:
    """Acota al tenant del request el queryset de los PrimaryKeyRelatedField
    listados en `tenant_scoped_fields`.

    Sin esto, un FK que cruza hacia OTRO modelo con su propio scoping (ej.
    `Product.category`, `Batch.product`, `CashRegister.branch`) aceptaría
    IDs de otro tenant, y el objeto creado terminaría con datos derivados
    de una company ajena (ver el caso real que motivó esto: sales.
    CashRegisterSerializer.branch, donde CashRegister.save() deriva
    `company` de `branch.company`). Se centraliza aquí en vez de repetir
    el mismo `__init__` acotando querysets en cada serializer.
    """

    tenant_scoped_fields = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request is None:
            return
        for field_name in self.tenant_scoped_fields:
            field = self.fields.get(field_name)
            if field is None or getattr(field, 'queryset', None) is None:
                continue
            field.queryset = field.queryset.model.objects.for_user(request.user)
