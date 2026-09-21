from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# Router DRF -- uniquement pour les ressources CRUD scopées au tenant
# courant (documents). `informations-primaires`/`publics`/`disponibilite`/
# `dossier`/`catalogue-documents-requis` restent des APIView dédiées :
# ce sont soit des singletons (pas de pk dans l'URL), soit des lectures
# publiques sans rapport avec un CRUD classique.
router = DefaultRouter()
router.register(r'documents-requis', views.TenantDocumentRequisViewSet, basename='tenant-document-requis')
router.register(r'documents-generiques', views.TenantDocumentGeneriqueViewSet, basename='tenant-document-generique')
router.register(r'tutelles', views.TenantTutelleViewSet, basename='tenant-tutelle')

urlpatterns = [
    path('disponibilite/', views.TenantDisponibiliteAPIView.as_view(), name='tenant-disponibilite'),
    path('publics/', views.TenantPublicsAPIView.as_view(), name='tenant-publics'),
    path('profil-public/<slug:sous_domaine>/', views.TenantProfilPublicAPIView.as_view(), name='tenant-profil-public'),
    path('identite/', views.TenantIdentiteAPIView.as_view(), name='tenant-identite'),
    path('informations-primaires/', views.TenantInformationsPrimairesAPIView.as_view(), name='tenant-informations-primaires'),
    path('catalogue-documents-requis/', views.TenantDocumentRequisCatalogueAPIView.as_view(), name='tenant-catalogue-documents-requis'),
    path('dossier/', views.TenantDossierAPIView.as_view(), name='tenant-dossier'),
    # IMPORTANT : doit rester AVANT `include(router.urls)` ci-dessous.
    # Les deux sont montés sur le même préfixe racine '' -- Django
    # résout les urlpatterns dans l'ORDRE et s'arrête au premier match.
    # `router.urls` inclut toujours une vue "API root" de DRF sur ''
    # (listant les viewsets enregistrés) : si elle était essayée EN
    # PREMIER, un GET/POST sur /api/tenants/v1/ (annuaire public /
    # création de tenant, endpoint existant) tomberait dessus au lieu
    # d'atteindre TenantCreateAPIView -- une régression complète de
    # fonctionnalités déjà en production. Cet ordre garantit que
    # TenantCreateAPIView reste prioritaire sur le chemin exact '', tout
    # en laissant `documents-requis/`/`documents-generiques/` (chemins
    # non vides) être résolus normalement par le router juste après.
    path('', views.TenantCreateAPIView.as_view(), name='tenant-create-list'),
    path('', include(router.urls)),
]