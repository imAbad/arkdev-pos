from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from core.models import BaseTenantModel


def product_image_upload_path(instance, filename):
    # Prefijo por tenant, como ya decidido en arquitectura_tecnica_pos.md
    # §4.3 — así el backend de Azure Blob (django-storages) no necesita
    # ningún cambio de convención cuando se active en producción.
    return f'tenant_{instance.company_id}/products/{filename}'


class Category(BaseTenantModel):
    """Extraído tal cual de pharma_core (decisiones_post_auditoria.md §2),
    con `company` no-nullable en vez de nullable — todo modelo de tenant
    la tiene siempre (CLAUDE.md #2), sin excepción."""

    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta(BaseTenantModel.Meta):
        verbose_name_plural = 'categories'
        constraints = [
            models.UniqueConstraint(fields=['company', 'name'], name='category_unique_company_name'),
            models.UniqueConstraint(fields=['company', 'slug'], name='category_unique_company_slug'),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Supplier(BaseTenantModel):
    """Extraído tal cual de pharma_core."""

    name = models.CharField(max_length=250)
    contact_name = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)

    def __str__(self):
        return self.name


class Product(BaseTenantModel):
    """Generalizado — sin campos de farmacia (health_fraction, drug_type,
    concentration_value, etc. de pharma_core no se portan). unit_type +
    variant_attributes generalizan granel/papelería/servicios en un solo
    modelo, en vez de una tabla de variantes rígida (ver
    decisiones_post_auditoria.md, pendiente #1 de arquitectura_tecnica_pos.md
    §10 si esto no alcanza para un caso real de variantes).

    Cómo `unit_type` se traduce a lógica de venta a granel (cantidad
    fraccionaria, precio por gramo/litro, báscula) es decisión de `sales`
    (punto 4 del orden de construcción), no de este modelo — aquí solo vive
    el dato.
    """

    class UnitType(models.TextChoices):
        PIEZA = 'PIEZA', 'Pieza'
        KG = 'KG', 'Kilogramo'
        GRAMO = 'GRAMO', 'Gramo'
        LITRO = 'LITRO', 'Litro'
        PAQUETE = 'PAQUETE', 'Paquete'
        SERVICIO = 'SERVICIO', 'Servicio'

    # Observación de sesión: qué unit_type admite cantidad fraccionaria en
    # una venta es una propiedad del TIPO de unidad, no de la venta —
    # vive aquí, sales.services.create_sale solo la consulta. Se cuentan
    # en enteros PIEZA/PAQUETE/SERVICIO (no tiene sentido vender "1.5
    # piezas", "1.5 paquetes" ni "1.5 servicios" — son unidades discretas);
    # KG/GRAMO/LITRO son las únicas fraccionarias porque se venden a
    # granel, por báscula o por medida.
    INTEGER_UNIT_TYPES = {UnitType.PIEZA, UnitType.PAQUETE, UnitType.SERVICIO}

    name = models.CharField(max_length=255)
    sku = models.CharField(max_length=50)
    barcode = models.CharField(max_length=100, null=True, blank=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='products')
    supplier = models.ForeignKey(
        Supplier, on_delete=models.SET_NULL, related_name='products', null=True, blank=True,
    )

    unit_type = models.CharField(max_length=10, choices=UnitType.choices, default=UnitType.PIEZA)
    # Reemplaza la obligatoriedad de lote de pharma_core: FEFO se vuelve
    # opcional por producto, no una exigencia de cada línea de venta (ver
    # decisiones_post_auditoria.md §3). No implica ninguna constraint de BD
    # que ate Product a Batch — ver catalog/tests/test_models.py.
    requires_batch = models.BooleanField(default=False)
    variant_attributes = models.JSONField(null=True, blank=True)

    cost_price = models.DecimalField(max_digits=12, decimal_places=2)
    sale_price = models.DecimalField(max_digits=12, decimal_places=2)
    # Reemplaza tax_percentage, huérfano en pharma_core (nunca se usaba en
    # el cálculo real — confirmado en la auditoría). Este sí se conecta al
    # cálculo de impuestos cuando sales.Sale exista (punto 4).
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    min_stock = models.PositiveIntegerField(default=0)

    # Agregado desde el diseño aunque no se use en MVP — evita migrar de
    # "URL en texto" a archivo real más adelante (arquitectura_tecnica_pos.md
    # §4.3). Storage local en dev; Azure Blob en producción vía settings.
    image = models.ImageField(upload_to=product_image_upload_path, null=True, blank=True)

    # Cross-sell simple (punto 5 de la sesión) — configurado a mano por el
    # administrador desde catálogo, no automático ni basado en historial de
    # compra (sobre-ingeniería para este tamaño de negocio, decisión
    # explícita). Simétrico a propósito: en retail chico "A sugiere B"
    # casi siempre implica "B sugiere A" (pan-mantequilla funciona en
    # ambos sentidos), y una relación simétrica evita mantener dos listas
    # independientes por par de productos para el caso común. Si algún día
    # se necesita una sugerencia direccional real, es un cambio deliberado
    # (symmetrical=False + related_name), no el default de hoy.
    related_products = models.ManyToManyField('self', blank=True)

    class Meta(BaseTenantModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=['company', 'sku'], name='product_unique_company_sku'),
            models.UniqueConstraint(
                fields=['company', 'barcode'],
                condition=models.Q(barcode__isnull=False),
                name='product_unique_company_barcode',
            ),
        ]

    @property
    def requires_integer_quantity(self):
        return self.unit_type in self.INTEGER_UNIT_TYPES

    def __str__(self):
        return f'{self.name} ({self.sku})'


class Batch(BaseTenantModel):
    """Lote — extraído de pharma_core, con dos cambios deliberados:
    `branch` ya no es nullable (un lote siempre entra a existencias de una
    sucursal concreta) y se agrega el UniqueConstraint (product,
    batch_number) que en pharma_core solo era una regla de dominio no
    forzada en BD (gap identificado al portar este modelo)."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='batches')
    branch = models.ForeignKey('tenants.Branch', on_delete=models.PROTECT, related_name='batches')
    batch_number = models.CharField(max_length=100)
    initial_quantity = models.PositiveIntegerField()
    current_quantity = models.PositiveIntegerField(editable=False)
    expiration_date = models.DateField()
    received_date = models.DateField(auto_now_add=True)

    class Meta(BaseTenantModel.Meta):
        ordering = ['expiration_date']
        constraints = [
            models.UniqueConstraint(fields=['product', 'batch_number'], name='batch_unique_product_batch_number'),
        ]

    def save(self, *args, **kwargs):
        if self._state.adding:
            self.current_quantity = self.initial_quantity
        self.company_id = self.product.company_id
        super().save(*args, **kwargs)

    @property
    def is_expired(self):
        return self.expiration_date < timezone.localdate()

    @property
    def days_to_expire(self):
        return (self.expiration_date - timezone.localdate()).days

    def can_be_sold(self):
        return self.current_quantity > 0 and not self.is_expired

    def __str__(self):
        return f'{self.product.name} · lote {self.batch_number}'


class InventoryAdjustment(BaseTenantModel):
    """Observación de sesión (ronda de 4 piezas, punto 4): reportado como
    "el ajuste manual de stock del punto 8" pero, al revisar el código,
    ese ajuste nunca se construyó — `StockTransfer`/`InventoryAdjustment`
    seguían listados como "pendientes de construir" en
    arquitectura_tecnica_pos.md §3, y `BatchSerializer` deja
    `current_quantity` de solo lectura a propósito (nada podía cambiarlo
    fuera de una venta). Este modelo es la construcción real, con motivo
    obligatorio desde el día uno — no un campo agregado después a algo
    que ya guardaba sin él.

    `batch` (no `product`) a propósito: el stock real vive en
    Batch.current_quantity (ver Product.requires_batch) — un ajuste sin
    lote no tendría ningún número que modificar, mismo hallazgo que ya
    limita catalog.services.low_stock_products/ProductSerializer.
    current_stock a productos con requires_batch=True.
    """

    class Reason(models.TextChoices):
        DAMAGE = 'DAMAGE', 'Merma/rotura'
        EXPIRATION = 'EXPIRATION', 'Caducidad no capturada por lote'
        THEFT = 'THEFT', 'Robo/faltante'
        COUNT_CORRECTION = 'COUNT_CORRECTION', 'Corrección de conteo'
        OTHER = 'OTHER', 'Otro'

    batch = models.ForeignKey(Batch, on_delete=models.PROTECT, related_name='adjustments')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='inventory_adjustments',
    )
    # Positivo o negativo — no solo bajas: una corrección de conteo puede
    # descubrir MÁS stock del registrado, no solo menos.
    quantity_delta = models.IntegerField()
    # Congelados al momento del ajuste (igual que SaleDetail.tax_rate_applied
    # congela la tasa vigente) — una auditoría posterior no debe depender
    # de recalcular contra el estado actual del lote, que ya cambió.
    quantity_before = models.PositiveIntegerField()
    quantity_after = models.PositiveIntegerField()
    reason = models.CharField(max_length=20, choices=Reason.choices)
    # Solo se exige que traiga texto cuando reason='OTHER' — validado en
    # catalog.services.adjust_batch_stock, no aquí (blank=True a nivel de
    # columna porque para el resto de motivos es opcional).
    reason_detail = models.CharField(max_length=200, blank=True)

    class Meta(BaseTenantModel.Meta):
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        self.company_id = self.batch.company_id
        super().save(*args, **kwargs)

    def __str__(self):
        return f'Ajuste {self.batch.product.name} {self.quantity_delta:+d} · {self.get_reason_display()}'
