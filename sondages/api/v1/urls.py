from rest_framework.routers import DefaultRouter

from .views import SondageViewSet

router = DefaultRouter()
router.register('sondages', SondageViewSet, basename='sondage')

urlpatterns = router.urls
