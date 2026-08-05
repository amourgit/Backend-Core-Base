from django.core.cache import cache
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView
from rest_framework.response import Response

from . import services
from .serializers import StatistiquesGlobalesSerializer

CACHE_KEY = 'statistiques:globales'
CACHE_TTL_SECONDES = 120  # Agrégations coûteuses : on évite de les recalculer à chaque requête.


class StatistiquesGlobalesView(APIView):
    """GET /statistiques/v1/globales/ — statistiques déjà calculées et
    prêtes à afficher, sans aucune manipulation nécessaire côté frontend."""

    permission_classes = [AllowAny]

    def get(self, request):
        donnees = cache.get(CACHE_KEY)
        if donnees is None:
            donnees = services.calculer_statistiques_globales()
            cache.set(CACHE_KEY, donnees, CACHE_TTL_SECONDES)

        serializer = StatistiquesGlobalesSerializer(donnees)
        return Response(serializer.data)
