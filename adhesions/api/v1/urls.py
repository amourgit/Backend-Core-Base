from rest_framework.routers import DefaultRouter

from .views import MembreTenantViewSet

router = DefaultRouter()
router.register('membres', MembreTenantViewSet, basename='membre-tenant')

urlpatterns = router.urls
