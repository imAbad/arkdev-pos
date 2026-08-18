from rest_framework.routers import DefaultRouter

from customers.viewsets import ClientViewSet, CreditAccountViewSet

router = DefaultRouter()
router.register('clients', ClientViewSet, basename='client')
router.register('credit-accounts', CreditAccountViewSet, basename='credit-account')

urlpatterns = router.urls
