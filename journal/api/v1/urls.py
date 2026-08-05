from rest_framework.routers import DefaultRouter

from .views import EvenementJournalViewSet

router = DefaultRouter()
router.register('evenements', EvenementJournalViewSet, basename='evenement-journal')

urlpatterns = router.urls
