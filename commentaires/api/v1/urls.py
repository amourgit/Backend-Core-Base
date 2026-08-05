from rest_framework.routers import DefaultRouter

from .views import CommentaireViewSet

router = DefaultRouter()
router.register('commentaires', CommentaireViewSet, basename='commentaire')

urlpatterns = router.urls
