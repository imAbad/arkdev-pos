from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from rest_framework_simplejwt.views import TokenRefreshView

from tenants.viewsets import IdentifierTokenObtainPairView, RequestSupervisorAuthorizationView

urlpatterns = [
    path('admin/', admin.site.urls),
    # Único endpoint de login — acepta username O email (ver
    # tenants.serializers.IdentifierTokenObtainPairSerializer). No hay
    # un segundo endpoint para un identificador distinto.
    path('api/v1/auth/token/', IdentifierTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/v1/auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path(
        'api/v1/auth/authorize-exception/',
        RequestSupervisorAuthorizationView.as_view(),
        name='authorize_exception',
    ),
    path('api/v1/', include('tenants.urls')),
    path('api/v1/', include('sales.urls')),
    path('api/v1/', include('catalog.urls')),
    path('api/v1/', include('customers.urls')),
    path('api/v1/', include('reports.urls')),
]

# Observación de sesión, punto 4 — causa raíz real de "el logo no se
# muestra" (probado con .ico/.png/.jpg, ningún formato/tamaño era el
# problema): el archivo SÍ se guardaba bien en disco (MEDIA_ROOT
# correcto) pero Django nunca tenía una ruta que sirviera `/media/...` —
# faltaba este helper. `static()` es un no-op automático cuando
# DEBUG=False (Django lo resuelve solo, ver su código fuente), así que es
# seguro dejarlo sin envolver en un if — en producción real la sirve
# el servidor web (o Azure Blob Storage cuando se configure, ver
# arquitectura_tecnica_pos.md §4.3), no Django.
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
