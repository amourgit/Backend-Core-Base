from django.core.cache import cache
from django.db import connection
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response

from . import services
from .serializers import MesStatistiquesSerializer, StatistiquesGlobalesSerializer

CACHE_KEY_PREFIX = 'statistiques:globales'
CACHE_KEY_PREFIX_MOI = 'statistiques:moi'
CACHE_TTL_SECONDES = 30  # Agrégations coûteuses : on évite de les recalculer
# à chaque requête -- mais 30s (et non 120s) pour qu'un administrateur qui
# publie une News puis consulte immédiatement le tableau de bord ne reste
# pas devant des chiffres visiblement obsolètes plusieurs minutes.


class StatistiquesGlobalesView(APIView):
    """GET /statistiques/v1/globales/ — statistiques déjà calculées et
    prêtes à afficher, sans aucune manipulation nécessaire côté frontend."""

    permission_classes = [AllowAny]

    def get(self, request):
        # La clé DOIT être scopée par tenant (schema_name) : le cache
        # Django (cache.get/set) est un système global, totalement
        # indépendant du changement de schéma PostgreSQL effectué par
        # TenantMiddleware pour cette requête. Une clé fixe partagée par
        # tous les tenants signifiait que les statistiques d'un tenant
        # pouvaient apparaître chez un autre -- ou être écrasées par lui --
        # dès qu'il y a plus d'un tenant actif sur ce même processus, ce
        # qui est justement l'objectif de cette architecture multi-tenant.
        cache_key = f'{CACHE_KEY_PREFIX}:{connection.schema_name}'
        donnees = cache.get(cache_key)
        if donnees is None:
            donnees = services.calculer_statistiques_globales()
            cache.set(cache_key, donnees, CACHE_TTL_SECONDES)

        serializer = StatistiquesGlobalesSerializer(donnees)
        return Response(serializer.data)


class MesStatistiquesView(APIView):
    """GET /statistiques/v1/moi/ — statistiques PERSONNELLES de
    l'utilisateur authentifié (contributions, interactions/réactions,
    sondages, contenus favoris, activité récente), déjà calculées et
    catégorisées côté serveur : le frontend n'a qu'à afficher.

    Volontairement séparé de UtilisateurPublicSerializer.get_stats() (voir
    users/api/v1/serializers.py) -- voir le commentaire en tête de
    services.calculer_statistiques_utilisateur pour la raison (N+1 évité
    partout ailleurs dans l'app où un auteur est affiché)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Clé scopée par tenant ET par utilisateur (même raison que
        # StatistiquesGlobalesView pour le tenant ; par utilisateur car
        # ces statistiques sont individuelles, contrairement aux globales).
        cache_key = f'{CACHE_KEY_PREFIX_MOI}:{connection.schema_name}:{request.user.pk}'
        donnees = cache.get(cache_key)
        if donnees is None:
            donnees = services.calculer_statistiques_utilisateur(request.user, request=request)
            cache.set(cache_key, donnees, CACHE_TTL_SECONDES)

        serializer = MesStatistiquesSerializer(donnees)
        return Response(serializer.data)
