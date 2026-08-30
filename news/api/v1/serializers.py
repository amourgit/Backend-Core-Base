"""
news/api/v1/serializers.py
============================

Le serializer `NewsSerializer` restitue EXACTEMENT la forme attendue par
`NewsSchema` (src/types/models/news.types.ts) côté frontend : toutes les
statistiques (`stats`) sont calculées côté backend à partir des tables
de faits (ReactionNews, NewsVue, votes des sondages liés, commentaires),
jamais renvoyées comme des compteurs dénormalisés qui pourraient dériver.
"""

from django.db.models import Count
from rest_framework import serializers

from referentiels.models import Categorie, Organisation, Etablissement
from users.api.v1.serializers import UtilisateurPublicSerializer
from ... import models


class CategorieNesteeSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='pk', read_only=True)

    class Meta:
        model = Categorie
        fields = ('id', 'nom', 'couleur', 'icone')


class OrganisationNesteeSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='pk', read_only=True)
    logo = serializers.SerializerMethodField()

    class Meta:
        model = Organisation
        fields = ('id', 'nom', 'logo', 'type', 'description')

    def get_logo(self, obj):
        if not obj.logo:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(obj.logo.url) if request else obj.logo.url


class EtablissementNesteeSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='pk', read_only=True)

    class Meta:
        model = Etablissement
        fields = ('id', 'nom', 'province')


class DocumentJointSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='pk', read_only=True)
    url = serializers.SerializerMethodField()

    class Meta:
        model = models.DocumentJoint
        fields = ('id', 'nom', 'url', 'taille', 'type')

    def get_url(self, obj):
        if not obj.fichier:
            return ''
        request = self.context.get('request')
        return request.build_absolute_uri(obj.fichier.url) if request else obj.fichier.url


class NewsMediaSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='pk', read_only=True)
    url = serializers.SerializerMethodField()
    thumbnail = serializers.SerializerMethodField()
    date = serializers.DateTimeField(source='cree_le', read_only=True)
    vues = serializers.SerializerMethodField()

    class Meta:
        model = models.NewsMedia
        fields = ('id', 'type', 'url', 'thumbnail', 'titre', 'description', 'duree', 'vues', 'date')

    def get_url(self, obj):
        request = self.context.get('request')
        if obj.fichier:
            return request.build_absolute_uri(obj.fichier.url) if request else obj.fichier.url
        return obj.url_externe

    def get_thumbnail(self, obj):
        if not obj.vignette:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(obj.vignette.url) if request else obj.vignette.url

    def get_vues(self, obj):
        return 0


class NewsListSerializer(serializers.ModelSerializer):
    """Version allégée utilisée pour les listings — sans les sous-collections
    lourdes (documents, médias, sondages complets)."""

    id = serializers.CharField(source='pk', read_only=True)
    image = serializers.SerializerMethodField()
    auteur = UtilisateurPublicSerializer(read_only=True)
    organisation = OrganisationNesteeSerializer(read_only=True)
    etablissement = EtablissementNesteeSerializer(read_only=True)
    categorie = CategorieNesteeSerializer(read_only=True)
    tags = serializers.SlugRelatedField(slug_field='nom', many=True, read_only=True)
    created_at = serializers.DateTimeField(source='cree_le', read_only=True)
    updated_at = serializers.DateTimeField(source='modifie_le', read_only=True)
    date_debut = serializers.DateTimeField(required=False, allow_null=True)
    date_fin = serializers.DateTimeField(required=False, allow_null=True)
    stats = serializers.SerializerMethodField()
    user_reaction = serializers.SerializerMethodField()
    reacteurs_recents = serializers.SerializerMethodField()

    class Meta:
        model = models.News
        fields = (
            'id', 'slug', 'type', 'titre', 'description', 'image', 'auteur',
            'organisation', 'etablissement', 'categorie', 'tags', 'province', 'lieu',
            'date_debut', 'date_fin', 'created_at', 'updated_at', 'statut', 'visibilite',
            'stats', 'user_reaction', 'reacteurs_recents',
        )

    def get_image(self, obj):
        if not obj.image:
            return ''
        request = self.context.get('request')
        return request.build_absolute_uri(obj.image.url) if request else obj.image.url

    def get_stats(self, obj):
        return calculer_stats_news(obj)

    def get_reacteurs_recents(self, obj):
        # Pile d'avatars affichée sur la card (voir NewsCard.tsx) : les
        # réactions étant illimitées par utilisateur (décision produit,
        # voir ReactionNews), on déduplique par utilisateur -- "sans
        # doublant" -- et on exclut les réactions anonymes
        # (utilisateur=None), qui n'ont aucun profil à afficher. Limité à
        # 5, la pile n'a pas vocation à tout montrer.
        utilisateurs = []
        vus = set()
        for reaction in obj.reactions.filter(
            type_reaction=models.TypeReaction.COEUR, utilisateur__isnull=False
        ).select_related('utilisateur').order_by('-cree_le'):
            if reaction.utilisateur_id in vus:
                continue
            vus.add(reaction.utilisateur_id)
            utilisateurs.append(reaction.utilisateur)
            if len(utilisateurs) >= 5:
                break
        from users.api.v1.serializers import UtilisateurPublicSerializer
        return UtilisateurPublicSerializer(utilisateurs, many=True, context=self.context).data

    def get_user_reaction(self, obj):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if not (user and user.is_authenticated):
            return None
        # Plusieurs réactions par utilisateur sont désormais possibles
        # (décision produit, aucune contrainte d'unicité) : on retient la
        # plus récente plutôt qu'une valeur arbitraire, purement à titre
        # informatif pour l'affichage initial du bouton.
        reaction = obj.reactions.filter(utilisateur=user).order_by('-cree_le').first()
        return reaction.type_reaction if reaction else None


class NewsSerializer(NewsListSerializer):
    """Version complète (détail) : inclut documents, médias, galerie,
    sondages liés et le lien de publication actif le plus récent."""

    contenu = serializers.CharField(required=False, allow_blank=True)
    galerie = serializers.SerializerMethodField()
    documents = DocumentJointSerializer(many=True, read_only=True)
    medias = NewsMediaSerializer(many=True, read_only=True)
    sondages = serializers.SerializerMethodField()
    lien_publication = serializers.SerializerMethodField()

    class Meta(NewsListSerializer.Meta):
        fields = NewsListSerializer.Meta.fields + (
            'contenu', 'galerie', 'documents', 'medias', 'sondages', 'lien_publication',
        )

    def get_galerie(self, obj):
        request = self.context.get('request')
        return [
            request.build_absolute_uri(img.image.url) if request else img.image.url
            for img in obj.galerie.all()
        ]

    def get_sondages(self, obj):
        from sondages.api.v1.serializers import SondageSerializer
        request = self.context.get('request')
        return SondageSerializer(obj.sondages.all(), many=True, context={'request': request}).data

    def get_lien_publication(self, obj):
        from liens.api.v1.serializers import LienPublicationSerializer
        request = self.context.get('request')
        lien = obj.liens_publication.order_by('-cree_le').first() if hasattr(obj, 'liens_publication') else None
        return LienPublicationSerializer(lien, context={'request': request}).data if lien else None


def calculer_stats_news(news_obj):
    """Calcule les statistiques d'une News à la volée — jamais de compteur
    dénormalisé stocké en base."""
    reactions_par_type = dict(
        news_obj.reactions.values_list('type_reaction').annotate(total=Count('id')).order_by()
    )
    total_votes_sondages = 0
    for sondage in news_obj.sondages.all():
        total_votes_sondages += sondage.votes.count()

    return {
        'vues': news_obj.vues.count(),
        'commentaires': news_obj.commentaires.filter(supprime_le__isnull=True).count() if hasattr(news_obj, 'commentaires') else 0,
        'reactions': {
            'coeur': reactions_par_type.get('coeur', 0),
            'jaime': reactions_par_type.get('jaime', 0),
            'bravo': reactions_par_type.get('bravo', 0),
            'youpi': reactions_par_type.get('youpi', 0),
            'wow': reactions_par_type.get('wow', 0),
            'jaimepas': reactions_par_type.get('jaimepas', 0),
        },
        'votes': total_votes_sondages,
        'partages': news_obj.partages,
    }


class NewsMediaEcritureSerializer(serializers.ModelSerializer):
    """Serializer d'écriture pour les médias riches d'une News —
    endpoint dédié /news/v1/medias/ (voir views.py:NewsMediaViewSet),
    filtré par `?news=<id>`. `news` est requis en écriture (non imbriqué
    sous /news/{id}/, même convention que commentaires/sondages/liens)."""

    class Meta:
        model = models.NewsMedia
        fields = (
            'id', 'news', 'type', 'fichier', 'url_externe', 'vignette',
            'titre', 'description', 'duree', 'ordre',
        )


class NewsImageGalerieSerializer(serializers.ModelSerializer):
    """Lecture ET écriture (modèle simple, un seul serializer suffit —
    pas de champs calculés à masquer en écriture comme sur News/Sondage)."""

    id = serializers.CharField(source='pk', read_only=True)
    # `pk_field=CharField()` : convention id-toujours-string de toute
    # l'API (voir NewsSerializer.id, DocumentJointSerializer.id...),
    # sinon ce SEUL champ renverrait un entier JSON brut.
    news = serializers.PrimaryKeyRelatedField(queryset=models.News.objects.all(), pk_field=serializers.CharField())
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = models.NewsImageGalerie
        # `image` reste requis (le modèle ne l'autorise pas vide,
        # `blank=True` n'est pas déclaré sur ce champ) : POST doit
        # toujours le fournir. PATCH (partial_update) reste possible
        # sans le refournir -- DRF ignore `required` en mode partiel.
        fields = ('id', 'news', 'image', 'image_url', 'legende', 'ordre')
        extra_kwargs = {'image': {'write_only': True}}

    def get_image_url(self, obj):
        if not obj.image:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(obj.image.url) if request else obj.image.url


class DocumentJointEcritureSerializer(serializers.ModelSerializer):
    """`taille`/`type` sont calculés côté modèle (DocumentJoint.save) —
    jamais fournis par le client, voir models.py."""

    class Meta:
        model = models.DocumentJoint
        fields = ('id', 'news', 'nom', 'fichier', 'taille', 'type')
        read_only_fields = ('taille', 'type')


class NewsEcritureSerializer(serializers.ModelSerializer):
    """Serializer de création/édition — champs simples uniquement (les
    sous-collections passent par leurs propres endpoints dédiés)."""

    # write_only : ce champ n'accepte QUE des noms de tags en entrée (voir
    # _resoudre_tags ci-dessous, qui les convertit en instances Tag). Sans
    # write_only, DRF tente aussi de s'en servir pour REPRÉSENTER la
    # relation M2M `News.tags` en sortie (ex: juste après un POST/PATCH,
    # quand ModelViewSet construit sa réponse) -- or ListField.to_representation
    # itère directement sur l'attribut, sans jamais appeler `.all()` comme le
    # fait ManyRelatedField (voir NewsListSerializer.tags, qui utilise
    # SlugRelatedField(many=True) pour la lecture, correctement). Résultat
    # sans ce write_only : `TypeError: 'ManyRelatedManager' object is not
    # iterable` -- 500 à chaque création/édition contenant des tags.
    tags = serializers.ListField(
        child=serializers.CharField(max_length=50), required=False, default=list, write_only=True,
    )

    class Meta:
        model = models.News
        fields = (
            'slug', 'type', 'titre', 'description', 'contenu', 'image',
            'organisation', 'etablissement', 'categorie', 'tags',
            'province', 'lieu', 'date_debut', 'date_fin', 'statut', 'visibilite',
        )
        # `slug` n'a pas `blank=True` au niveau du modèle (voir news/models.py) :
        # sans ce read_only, DRF l'expose comme un champ REQUIS côté client
        # ("Ce champ est obligatoire.", 400) -- alors qu'il est TOUJOURS
        # généré côté serveur à partir du titre (voir
        # NewsViewSet.perform_create -> services.generer_slug_unique), jamais
        # fourni par le frontend (NewsEcriturePayload.slug est d'ailleurs
        # optionnel côté TypeScript, voir news.repository.ts). Sur update,
        # perform_update() ne le régénère pas : il reste simplement inchangé,
        # comportement voulu (une édition ne doit pas faire bouger l'URL
        # publique d'une News déjà publiée).
        read_only_fields = ('slug',)

    def _resoudre_tags(self, noms_tags):
        tags = []
        for nom in noms_tags:
            nom = nom.strip()
            if not nom:
                continue
            tag, _created = models.Tag.objects.get_or_create(nom=nom)
            tags.append(tag)
        return tags

    def create(self, validated_data):
        noms_tags = validated_data.pop('tags', [])
        news = models.News.objects.create(**validated_data)
        if noms_tags:
            news.tags.set(self._resoudre_tags(noms_tags))
        return news

    def update(self, instance, validated_data):
        noms_tags = validated_data.pop('tags', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if noms_tags is not None:
            instance.tags.set(self._resoudre_tags(noms_tags))
        return instance
