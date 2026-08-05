from django_filters.rest_framework import DjangoFilterBackend

from common.drf import LectureSeuleModelViewSet
from common.permissions import EstModerateurOuAdmin
from ... import models
from .serializers import EvenementJournalSerializer


class EvenementJournalViewSet(LectureSeuleModelViewSet):
    """GET /journal/v1/evenements/ — journal d'audit, lecture seule."""
    queryset = models.EvenementJournal.objects.all().select_related('cree_par').order_by('-cree_le')
    serializer_class = EvenementJournalSerializer
    permission_classes = [EstModerateurOuAdmin]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['action']
