from rest_framework.filters import SearchFilter
from django_filters.rest_framework import DjangoFilterBackend

from common.drf import SocleModelViewSet
from common.permissions import LectureLibreEcritureModerateur
from referentiels.models import Categorie, Organisation, Etablissement
from .serializers import CategorieSerializer, OrganisationSerializer, EtablissementSerializer


class CategorieViewSet(SocleModelViewSet):
    queryset = Categorie.objects.actifs()
    serializer_class = CategorieSerializer
    permission_classes = [LectureLibreEcritureModerateur]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['statut']
    search_fields = ['nom']


class OrganisationViewSet(SocleModelViewSet):
    queryset = Organisation.objects.actifs()
    serializer_class = OrganisationSerializer
    permission_classes = [LectureLibreEcritureModerateur]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['type', 'statut']
    search_fields = ['nom']


class EtablissementViewSet(SocleModelViewSet):
    queryset = Etablissement.objects.actifs()
    serializer_class = EtablissementSerializer
    permission_classes = [LectureLibreEcritureModerateur]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['province', 'statut']
    search_fields = ['nom', 'province']
