from rest_framework.routers import DefaultRouter

from .views import SignalementViewSet, UtilisateursAdminViewSet

router = DefaultRouter()
router.register('signalements', SignalementViewSet, basename='signalement')
router.register('utilisateurs', UtilisateursAdminViewSet, basename='utilisateur-admin')

urlpatterns = router.urls
