from rest_framework.routers import DefaultRouter

from .views import NewsViewSet, NewsMediaViewSet, NewsImageGalerieViewSet, DocumentJointViewSet

router = DefaultRouter()
router.register('news', NewsViewSet, basename='news')
router.register('medias', NewsMediaViewSet, basename='news-media')
router.register('galerie', NewsImageGalerieViewSet, basename='news-galerie')
router.register('documents', DocumentJointViewSet, basename='news-document')

urlpatterns = router.urls
