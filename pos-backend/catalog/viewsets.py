from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from catalog.models import Batch, Category, Product, Supplier
from catalog.serializers import (
    BatchSerializer,
    CategorySerializer,
    InventoryAdjustmentInputSerializer,
    InventoryAdjustmentSerializer,
    ProductSerializer,
    SupplierSerializer,
)
from catalog.services import InventoryAdjustmentError, adjust_batch_stock
from core.mixins import TenantScopedViewSetMixin
from core.permissions import IsAdministratorOrReadOnly, IsAdministratorOrSupervisor


class CategoryViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    # Punto 8: estructura de catálogo (categorías/proveedores), igual que
    # Product — cualquiera lee, solo ADMINISTRADOR escribe. Bug real
    # encontrado al revisar este viewset para el punto 8: no tenía NINGÚN
    # gate propio, heredaba solo IsAuthenticated — cualquier cajero podía
    # crear/borrar categorías (mismo patrón de gap ya encontrado y
    # corregido en CompanySettingsViewSet/ProductViewSet, puntos 3 y 5).
    permission_classes = [IsAuthenticated, IsAdministratorOrReadOnly]


class SupplierViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer
    permission_classes = [IsAuthenticated, IsAdministratorOrReadOnly]


class ProductViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    # Cualquier cajero autenticado puede LEER (el buscador de venta lo
    # necesita), pero editar catálogo/precio/relacionados es exclusivo de
    # ADMINISTRADOR (punto 8 lo formaliza para el resto de catalog, pero
    # este gate ya aplica aquí desde el punto 5 — related_products se
    # edita por este mismo endpoint).
    permission_classes = [IsAuthenticated, IsAdministratorOrReadOnly]
    # ?search= por nombre/sku/barcode — lo primero que necesita cualquier
    # pantalla de venta real (buscar producto), agregado al leer el
    # endpoint desde la perspectiva del frontend (punto 7).
    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'sku', 'barcode']


class BatchViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Batch.objects.all()
    serializer_class = BatchSerializer
    # Punto 8: lotes/existencias (nuevos lotes, ajustes de stock) son
    # operación de inventario — ADMINISTRADOR o Supervisor (CAJERO con
    # can_authorize_exceptions), no cualquier cajero. A diferencia de
    # Product, ningún flujo de venta llama a este endpoint directo (el
    # descuento de stock en una venta pasa por
    # sales.services/catalog.services server-side, no por
    # POST/PATCH /batches/), así que no hay necesidad de dejar lectura
    # abierta a todos como con Product — mismo gate en lectura y
    # escritura. Otro gap real encontrado igual que Category/Supplier:
    # este viewset solo tenía IsAuthenticated.
    permission_classes = [IsAuthenticated, IsAdministratorOrSupervisor]

    def get_queryset(self):
        # Observación de sesión, punto 2: la pantalla de Inventario
        # necesita los lotes de UN producto a la vez — sin django-filter
        # instalado (no se agrega solo por esto), se filtra a mano igual
        # que SaleViewSet.get_queryset() ya hace con date_from/date_to.
        qs = super().get_queryset().order_by('expiration_date')
        product_id = self.request.query_params.get('product')
        if product_id:
            qs = qs.filter(product_id=product_id)
        return qs

    @action(detail=True, methods=['post'])
    def adjust(self, request, pk=None):
        # Observación de sesión (ronda de 4 piezas, punto 4): único camino
        # para cambiar current_quantity fuera de una venta —
        # BatchSerializer lo deja de solo lectura a propósito (ver
        # catalog.models.InventoryAdjustment). Motivo obligatorio, sin
        # excepción: no se puede llamar a esta acción sin él.
        batch = self.get_object()
        input_serializer = InventoryAdjustmentInputSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        data = input_serializer.validated_data
        try:
            adjustment = adjust_batch_stock(
                batch=batch, quantity_delta=data['quantity_delta'], reason=data['reason'],
                reason_detail=data.get('reason_detail', ''), actor=request.user,
            )
        except InventoryAdjustmentError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(InventoryAdjustmentSerializer(adjustment).data, status=status.HTTP_201_CREATED)
