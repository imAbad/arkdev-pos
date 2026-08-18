from django.contrib import admin
from django.urls import include, path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from tenants.viewsets import RequestSupervisorAuthorizationView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/auth/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
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
