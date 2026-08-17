from django.utils import timezone
from rest_framework import serializers

from common.permissions import a_role, ROLES_MODERATION
from users.api.v1.serializers import UtilisateurPublicSerializer
from ... import models


class ChoixSondageSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='pk', read_only=True)
    image = serializers.SerializerMethodField()
    nombre_votes = serializers.SerializerMethodField()
    pourcentage = serializers.SerializerMethodField()

    class Meta:
        model = models.ChoixSondage
        fields = ('id', 'libelle', 'image', 'nombre_votes', 'pourcentage')

    def get_image(self, obj):
        if not obj.image:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(obj.image.url) if request else obj.image.url

    def _resultats_visibles(self):
        # Par défaut (contexte non fourni, ex: usage hors SondageSerializer),
        # on ne masque rien -- le masquage est une décision prise une seule
        # fois par SondageSerializer._resultats_visibles et propagée ici via
        # le contexte, jamais recalculée par choix (résultat incohérent sinon
        # entre deux choix d'un même sondage).
        return self.context.get('resultats_visibles', True)

    def get_nombre_votes(self, obj):
        if not self._resultats_visibles():
            return 0
        return obj.votes.count()

    def get_pourcentage(self, obj):
        if not self._resultats_visibles():
            return 0.0
        total = self.context.get('total_votants') or 0
        if total == 0:
            return 0.0
        return round(obj.votes.count() / total * 100, 1)


class SondageSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='pk', read_only=True)
    news_id = serializers.CharField(read_only=True)
    sujet_id = serializers.CharField(source='news_id', read_only=True)
    image = serializers.SerializerMethodField()
    choix = serializers.SerializerMethodField()
    total_votes = serializers.SerializerMethodField()
    user_voted_choice_ids = serializers.SerializerMethodField()
    resultats_visibles = serializers.SerializerMethodField()
    # Métadonnées communes -- même convention que NewsListSerializer et
    # CommentaireSerializer (news/api/v1/serializers.py,
    # commentaires/api/v1/serializers.py) : `auteur`/`created_at`/
    # `updated_at` exposés à partir du Socle de Traçabilité
    # (`cree_par`/`cree_le`/`modifie_le`). Absents jusqu'ici sur les
    # sondages alors que le modèle les porte déjà -- c'est ce qui rendait
    # les métadonnées communes incomplètes côté API.
    auteur = UtilisateurPublicSerializer(source='cree_par', read_only=True)
    created_at = serializers.DateTimeField(source='cree_le', read_only=True)
    updated_at = serializers.DateTimeField(source='modifie_le', read_only=True)

    class Meta:
        model = models.Sondage
        fields = (
            'id', 'news_id', 'sujet_id', 'titre', 'description', 'question', 'image', 'choix',
            'date_debut', 'date_fin', 'type_vote', 'anonymat', 'visibilite_resultat', 'statut',
            'total_votes', 'user_voted_choice_ids', 'resultats_visibles',
            'auteur', 'created_at', 'updated_at',
        )

    def get_image(self, obj):
        if not obj.image:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(obj.image.url) if request else obj.image.url

    def _total_votants(self, obj):
        return obj.votes.values('utilisateur_id').distinct().count()

    def _resultats_visibles(self, obj):
        """Applique `visibilite_resultat` == MASQUE_JUSQUA_FIN : les
        décomptes ne sont pas exposés avant `date_fin`, sauf pour :
          - un sondage déjà clos (date_fin dépassée) ;
          - un modérateur/l'auteur du sondage (visibilité de contrôle) ;
          - un utilisateur qui a déjà voté (il peut voir où se situe son
            propre vote une fois qu'il s'est prononcé -- c'est le
            comportement déjà anticipé côté frontend, voir SondageCard.tsx
            :  `showResults = hasVoted || visibiliteResultat === 'instantane'`
            -- jusqu'ici purement client, donc contournable : les décomptes
            réels étaient toujours renvoyés bruts par l'API quel que soit
            `visibilite_resultat`. Ce calcul fait maintenant foi côté
            serveur, le frontend n'a plus qu'à lire `resultats_visibles`).
        """
        if obj.visibilite_resultat != models.VisibiliteResultatSondage.MASQUE_JUSQUA_FIN:
            return True
        if timezone.now() >= obj.date_fin:
            return True
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if not (user and user.is_authenticated):
            return False
        if a_role(user, 'organisation', *ROLES_MODERATION) or obj.cree_par_id == user.id:
            return True
        return obj.votes.filter(utilisateur=user).exists()

    def get_resultats_visibles(self, obj):
        return self._resultats_visibles(obj)

    def get_total_votes(self, obj):
        return self._total_votants(obj) if self._resultats_visibles(obj) else 0

    def get_choix(self, obj):
        request = self.context.get('request')
        total = self._total_votants(obj)
        visibles = self._resultats_visibles(obj)
        choix_qs = obj.choix.all()
        return ChoixSondageSerializer(
            choix_qs, many=True,
            context={'request': request, 'total_votants': total, 'resultats_visibles': visibles},
        ).data

    def get_user_voted_choice_ids(self, obj):
        # Toujours visible pour l'intéressé, indépendamment du masquage des
        # résultats agrégés ci-dessus : ce n'est pas "le résultat du
        # sondage", c'est la confirmation de SON PROPRE vote (nécessaire à
        # l'UI pour cocher les options déjà choisies et permettre de les
        # modifier/retirer -- voir sondages/api/v1/services.enregistrer_vote).
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if not (user and user.is_authenticated):
            return []
        return list(obj.votes.filter(utilisateur=user).values_list('choix_id', flat=True))


class SondageEcritureSerializer(serializers.ModelSerializer):
    choix = serializers.ListField(child=serializers.CharField(max_length=255), write_only=True, required=False)

    class Meta:
        model = models.Sondage
        # 'id' DOIT être listé : SondageViewSet.create() (views.py) relit
        # response.data['id'] juste après super().create() -- même bug
        # que CommentaireEcritureSerializer (voir commentaires/api/v1/
        # serializers.py), corrigé à l'identique ici.
        fields = (
            'id', 'news', 'titre', 'description', 'question', 'image', 'choix',
            'date_debut', 'date_fin', 'type_vote', 'anonymat', 'visibilite_resultat', 'statut',
        )

    def validate_choix(self, value):
        libelles = [libelle.strip() for libelle in value if libelle and libelle.strip()]
        if len(libelles) < 2:
            raise serializers.ValidationError('Un sondage nécessite au moins deux choix.')
        return libelles

    def validate(self, attrs):
        date_debut = attrs.get('date_debut', getattr(self.instance, 'date_debut', None))
        date_fin = attrs.get('date_fin', getattr(self.instance, 'date_fin', None))
        if date_debut and date_fin and date_fin <= date_debut:
            raise serializers.ValidationError({
                'date_fin': "La date de fin doit être postérieure à la date de début.",
            })
        return attrs

    def create(self, validated_data):
        libelles_choix = validated_data.pop('choix', [])
        sondage = models.Sondage.objects.create(**validated_data)
        for ordre, libelle in enumerate(libelles_choix):
            models.ChoixSondage.objects.create(sondage=sondage, libelle=libelle, ordre=ordre)
        return sondage
