from rest_framework.routers import DefaultRouter

from .views import CategorieViewSet, OrganisationViewSet, EtablissementViewSet

router = DefaultRouter()
router.register('categories', CategorieViewSet, basename='categorie')
router.register('organisations', OrganisationViewSet, basename='organisation')
router.register('etablissements', EtablissementViewSet, basename='etablissement')

urlpatterns = router.urls
