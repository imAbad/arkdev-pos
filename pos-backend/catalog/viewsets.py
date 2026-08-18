from rest_framework import filters, viewsets
from rest_framework.permissions import IsAuthenticated

from catalog.models import Batch, Category, Product, Supplier
from catalog.serializers import BatchSerializer, CategorySerializer, ProductSerializer, SupplierSerializer
from core.mixins import TenantScopedViewSetMixin
from core.permissions import IsAdministratorOrReadOnly


class CategoryViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticated]


class SupplierViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer
    permission_classes = [IsAuthenticated]


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
    permission_classes = [IsAuthenticated]
