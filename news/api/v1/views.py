from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from common.drf import SocleModelViewSet
from ... import models
from . import services
from .permissions import NewsPermission
from .serializers import NewsSerializer, NewsListSerializer, NewsEcritureSerializer


class NewsViewSet(SocleModelViewSet):
    """
    - GET  /news/v1/news/                liste (filtrée par visibilité)
    - GET  /news/v1/news/?auteur={id}     "mes publications" (page Profil) --
      combiné à get_queryset() ci-dessous (qui autorise déjà l'auteur à voir
      ses propres brouillons), ceci isole exactement SES publications,
      brouillons compris, sans exposer les brouillons des autres.
    - POST /news/v1/news/                création
    - GET  /news/v1/news/{slug|id}/       détail
    - PATCH/PUT /news/v1/news/{slug|id}/  édition
    - DELETE /news/v1/news/{slug|id}/     suppression logique
    - POST /news/v1/news/{id}/reactions/  réagir (toggle)
    - POST /news/v1/news/{id}/partager/   incrémenter le compteur de partages
    """
    permission_classes = [NewsPermission]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['type', 'categorie', 'province', 'statut', 'organisation', 'etablissement', 'auteur']
    search_fields = ['titre', 'description', 'tags__nom']
    ordering_fields = ['cree_le', 'modifie_le', 'titre']
    ordering = ['-cree_le']

    def get_queryset(self):
        qs = models.News.objects.actifs().select_related(
            'auteur', 'organisation', 'etablissement', 'categorie'
        ).prefetch_related('tags', 'documents', 'medias', 'galerie', 'sondages__choix', 'reactions')

        if getattr(self, 'swagger_fake_view', False):
            return qs.none()

        user = self.request.user
        if user and user.is_authenticated and getattr(user, 'role', None) in ('moderateur', 'administrateur'):
            return qs

        # Public : uniquement les News publiées et publiques, sauf pour
        # l'auteur qui voit aussi ses propres brouillons.
        from django.db.models import Q
        visibles = Q(statut=models.NewsStatutChoices.PUBLIE, visibilite=models.Visibilite.PUBLIC)
        if user and user.is_authenticated:
            visibles |= Q(auteur=user)
        return qs.filter(visibles)

    def get_serializer_class(self):
        if self.action == 'list':
            return NewsListSerializer
        if self.action in ('create', 'update', 'partial_update'):
            return NewsEcritureSerializer
        return NewsSerializer

    def get_object(self):
        """Permet la résolution par `slug` OU par identifiant numérique,
        pour matcher `NEWS_ENDPOINTS.detail(slugOrId)` côté frontend."""
        lookup = self.kwargs.get(self.lookup_url_kwarg or self.lookup_field)
        qs = self.filter_queryset(self.get_queryset())
        obj = qs.filter(slug=lookup).first()
        if obj is None and str(lookup).isdigit():
            obj = qs.filter(pk=lookup).first()
        if obj is None:
            raise NotFound('News introuvable.')
        self.check_object_permissions(self.request, obj)
        return obj

    def perform_create(self, serializer):
        user = self.request.user
        titre = serializer.validated_data.get('titre', '')
        slug = services.generer_slug_unique(titre)
        serializer.save(auteur=user, cree_par=user, slug=slug)

    def perform_update(self, serializer):
        user = self.request.user
        serializer.save(modifie_par=user, motif_derniere_modification='Mise à jour via API')

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        services.enregistrer_vue(instance, request.user if request.user.is_authenticated else None,
                                  adresse_ip=request.META.get('REMOTE_ADDR'))
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='reactions')
    def reagir(self, request, pk=None):
        news = self.get_object()
        type_reaction = request.data.get('reaction')
        if type_reaction not in models.TypeReaction.values:
            return Response({'detail': 'Type de réaction invalide.'}, status=status.HTTP_400_BAD_REQUEST)

        services.basculer_reaction(news, request.user, type_reaction)
        serializer = NewsSerializer(news, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='partager')
    def partager(self, request, pk=None):
        news = self.get_object()
        total = services.incrementer_partages(news)
        return Response({'partages': total})
