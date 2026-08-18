from rest_framework.routers import DefaultRouter

from tenants.viewsets import BranchViewSet, CompanySettingsViewSet, UserProfileViewSet

router = DefaultRouter()
router.register('branches', BranchViewSet, basename='branch')
router.register('company-settings', CompanySettingsViewSet, basename='company-settings')
router.register('user-profiles', UserProfileViewSet, basename='user-profile')

urlpatterns = router.urls
