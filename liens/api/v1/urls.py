from rest_framework.routers import DefaultRouter

from .views import LienPublicationViewSet

router = DefaultRouter()
router.register('liens', LienPublicationViewSet, basename='lien')

urlpatterns = router.urls
