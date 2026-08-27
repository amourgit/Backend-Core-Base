from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from common.drf import SocleModelViewSet
from ... import models
from . import services
from .permissions import NewsPermission, NewsSousRessourcePermission
from .serializers import (
    NewsSerializer, NewsListSerializer, NewsEcritureSerializer,
    NewsMediaSerializer, NewsMediaEcritureSerializer,
    NewsImageGalerieSerializer, DocumentJointSerializer, DocumentJointEcritureSerializer,
)


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

    def create(self, request, *args, **kwargs):
        # NewsEcritureSerializer ne restitue que les champs scalaires
        # (voir son Meta.fields) -- on re-sérialise avec NewsSerializer pour
        # renvoyer la forme complète attendue par NewsSchema côté frontend
        # (auteur, stats, tags résolus, etc.), même pattern que
        # NewsMediaViewSet.create() / DocumentJointViewSet.create() ci-dessous.
        # On identifie l'instance créée par son slug : NewsEcritureSerializer
        # n'expose pas `id` (voir Meta.fields), seulement `slug`.
        response = super().create(request, *args, **kwargs)
        news = self.get_queryset().get(slug=response.data['slug'])
        return Response(
            NewsSerializer(news, context=self.get_serializer_context()).data, status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        news = self.get_queryset().get(slug=response.data['slug'])
        return Response(NewsSerializer(news, context=self.get_serializer_context()).data)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        services.enregistrer_vue(instance, request.user if request.user.is_authenticated else None,
                                  adresse_ip=request.META.get('REMOTE_ADDR'))
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='reactions', authentication_classes=[])
    def reagir(self, request, pk=None):
        news = self.get_object()
        type_reaction = request.data.get('reaction')
        if type_reaction not in models.TypeReaction.values:
            return Response({'detail': 'Type de réaction invalide.'}, status=status.HTTP_400_BAD_REQUEST)

        # Permettre les réactions anonymes (utilisateur = None si non authentifié)
        utilisateur = request.user if request.user.is_authenticated else None
        services.ajouter_reaction(news, utilisateur, type_reaction)
        serializer = NewsSerializer(news, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='partager')
    def partager(self, request, pk=None):
        news = self.get_object()
        total = services.incrementer_partages(news)
        return Response({'partages': total})


class NewsMediaViewSet(viewsets.ModelViewSet):
    """
    - GET/POST /news/v1/medias/?news={id}
    - GET/PATCH/DELETE /news/v1/medias/{id}/

    Endpoint dédié, app backend séparée du détail News (même convention
    que commentaires/sondages/liens — voir NewsPermission et
    CommentaireViewSet) : le frontend backoffice gère les médias riches
    d'une News (vidéo, audio, document intégré, image annotée) sans
    passer par NewsEcritureSerializer, qui ne couvre que les champs
    scalaires de News elle-même.
    """
    permission_classes = [NewsSousRessourcePermission]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['news']

    def get_queryset(self):
        return models.NewsMedia.objects.select_related('news').order_by('ordre', 'cree_le')

    def get_serializer_class(self):
        if self.action in ('create', 'update', 'partial_update'):
            return NewsMediaEcritureSerializer
        return NewsMediaSerializer

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        media = models.NewsMedia.objects.get(pk=response.data['id'])
        return Response(
            NewsMediaSerializer(media, context={'request': request}).data, status=status.HTTP_201_CREATED,
        )


class NewsImageGalerieViewSet(viewsets.ModelViewSet):
    """GET/POST /news/v1/galerie/?news={id} — GET/PATCH/DELETE /news/v1/galerie/{id}/"""
    permission_classes = [NewsSousRessourcePermission]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['news']
    serializer_class = NewsImageGalerieSerializer

    def get_queryset(self):
        return models.NewsImageGalerie.objects.select_related('news').order_by('ordre')


class DocumentJointViewSet(viewsets.ModelViewSet):
    """GET/POST /news/v1/documents/?news={id} — GET/PATCH/DELETE /news/v1/documents/{id}/"""
    permission_classes = [NewsSousRessourcePermission]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['news']

    def get_queryset(self):
        return models.DocumentJoint.objects.select_related('news').order_by('-cree_le')

    def get_serializer_class(self):
        if self.action in ('create', 'update', 'partial_update'):
            return DocumentJointEcritureSerializer
        return DocumentJointSerializer

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        document = models.DocumentJoint.objects.get(pk=response.data['id'])
        return Response(
            DocumentJointSerializer(document, context={'request': request}).data, status=status.HTTP_201_CREATED,
        )
