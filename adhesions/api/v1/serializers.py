from rest_framework import serializers
from django.contrib.auth import get_user_model

from adhesions.models import MembreTenant, Badge

User = get_user_model()


class BadgeSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='pk', read_only=True)

    class Meta:
        model = Badge
        fields = ('id', 'nom', 'icone', 'description')


class MembreTenantSerializer(serializers.ModelSerializer):
    """
    Représentation d'un membre DANS CE TENANT : combine son identité
    globale (users.User, schéma public -- username/email/avatar/noms)
    et ses attributs propres à CE tenant (rôle, organisation,
    établissement, badges, statut d'adhésion). `user_id` référence
    users.User.id SANS ForeignKey physique (voir adhesions/models.py) :
    l'identité globale est donc résolue ici via une requête séparée
    (recherche automatiquement le schéma public, `users` n'existant
    plus que là -- voir search_path), jamais par select_related.
    """
    id = serializers.CharField(source='pk', read_only=True)
    user_id = serializers.CharField(read_only=True)
    username = serializers.SerializerMethodField()
    nom_affiche = serializers.SerializerMethodField()
    email = serializers.SerializerMethodField()
    avatar = serializers.SerializerMethodField()
    badges = BadgeSerializer(many=True, read_only=True)
    etablissement_nom = serializers.CharField(source='etablissement.nom', read_only=True, default=None)
    organisation_nom = serializers.CharField(source='organisation.nom', read_only=True, default=None)

    class Meta:
        model = MembreTenant
        fields = (
            'id', 'user_id', 'username', 'nom_affiche', 'email', 'avatar',
            'role', 'organisation', 'organisation_nom', 'etablissement', 'etablissement_nom',
            'badges', 'statut_adhesion', 'demande_le', 'traitee_le', 'motif_refus',
        )
        read_only_fields = ('id', 'user_id', 'demande_le', 'traitee_le')

    def _utilisateur(self, obj):
        cache = self.context.setdefault('_utilisateurs_cache', {})
        if obj.user_id not in cache:
            cache[obj.user_id] = User.objects.filter(id=obj.user_id).first()
        return cache[obj.user_id]

    def get_username(self, obj):
        u = self._utilisateur(obj)
        return u.username if u else None

    def get_nom_affiche(self, obj):
        u = self._utilisateur(obj)
        if not u:
            return None
        full_name = u.get_full_name()
        return full_name if full_name != u.username else u.username

    def get_email(self, obj):
        u = self._utilisateur(obj)
        return u.email if u else None

    def get_avatar(self, obj):
        u = self._utilisateur(obj)
        if not (u and u.profile_picture):
            return None
        request = self.context.get('request')
        url = u.profile_picture.url
        return request.build_absolute_uri(url) if request else url


class MembreTenantRoleUpdateSerializer(serializers.ModelSerializer):
    """Édition réservée aux modérateurs/administrateurs (voir
    MembreTenantViewSet.permission_classes) : rôle et rattachements
    UNIQUEMENT -- le statut d'adhésion passe par l'action `traiter`."""

    class Meta:
        model = MembreTenant
        fields = ('role', 'organisation', 'etablissement')


class TraiterAdhesionSerializer(serializers.Serializer):
    accepter = serializers.BooleanField(required=True)
    motif = serializers.CharField(required=False, allow_blank=True, default='')
