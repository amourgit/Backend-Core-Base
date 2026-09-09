from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from .services import UsersService, normaliser_identifiant, is_email, is_telephone_valide

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    """
    Représentation ADMINISTRATIVE d'un compte GLOBAL (identité --
    schéma public uniquement) -- consommée par l'administration
    plateforme (superusers). Le rôle applicatif et les rattachements
    (organisation/établissement/badges), propres à CHAQUE tenant, ne
    sont plus portés par `User` depuis la réforme identité globale /
    adhésion tenant : voir `adhesions.MembreTenant` /
    MembreTenantSerializer (adhesions/api/v1/serializers.py) pour la
    gestion "membres de CE tenant" (backoffice par tenant).
    """

    class Meta:
        model = User
        fields = (
            'id', 'username', 'email', 'first_name', 'last_name', 'is_active', 'is_verified',
            'is_staff', 'is_superuser', 'date_joined', 'last_login', 'phone_number', 'address',
            'date_of_birth', 'language_preference', 'timezone',
        )
        read_only_fields = ('id', 'date_joined', 'last_login', 'is_staff', 'is_superuser')


class UtilisateurPublicSerializer(serializers.ModelSerializer):
    """
    Profil utilisateur public tel que consommé par le frontend — voir
    `Utilisateur` dans src/types/models/user.types.ts. Les identifiants
    numériques Django sont exposés en tant que chaînes (`id`) pour
    correspondre au contrat frontend, qui traite tous les identifiants
    comme des chaînes de façon uniforme.

    `role`/`etablissement`/`badges` restent dans le CONTRAT JSON
    (inchangé côté frontend) mais sont désormais résolus depuis
    `adhesions.MembreTenant` DANS LE TENANT COURANT (le schéma actif
    sur la connexion au moment de la sérialisation) plutôt que depuis
    des champs directs de `User` -- une même personne peut avoir un
    rôle différent d'un tenant à l'autre. Absence d'adhésion dans ce
    tenant -> `role`/`etablissement`/`badges` valent None/[] (comme un
    utilisateur sans rôle assigné auparavant).
    """
    id = serializers.CharField(source='pk', read_only=True)
    nom_affiche = serializers.SerializerMethodField()
    avatar = serializers.SerializerMethodField()
    role = serializers.SerializerMethodField()
    etablissement = serializers.SerializerMethodField()
    badges = serializers.SerializerMethodField()
    stats = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'username', 'nom_affiche', 'avatar', 'role', 'etablissement', 'email', 'badges', 'stats')

    def _membre(self, obj):
        from adhesions.api.v1.services import AdhesionService
        cache = self.context.setdefault('_membres_cache', {})
        if obj.pk not in cache:
            cache[obj.pk] = AdhesionService.get_membre(obj.pk)
        return cache[obj.pk]

    def get_nom_affiche(self, obj):
        full_name = obj.get_full_name()
        return full_name if full_name != obj.username else obj.username

    def get_avatar(self, obj):
        if obj.profile_picture:
            request = self.context.get('request')
            url = obj.profile_picture.url
            return request.build_absolute_uri(url) if request else url
        return None

    def get_role(self, obj):
        membre = self._membre(obj)
        return membre.role if membre else None

    def get_etablissement(self, obj):
        membre = self._membre(obj)
        return membre.etablissement.nom if (membre and membre.etablissement_id) else None

    def get_badges(self, obj):
        from adhesions.api.v1.serializers import BadgeSerializer
        membre = self._membre(obj)
        if not membre:
            return []
        return BadgeSerializer(membre.badges.all(), many=True).data

    def get_stats(self, obj):
        contributions_news = getattr(obj, 'news_publiees', None)
        contributions_commentaires = getattr(obj, 'commentaires_publies', None)
        votes_sondages = getattr(obj, 'votes_sondages', None)
        votes_commentaires = getattr(obj, 'votes_commentaires', None)

        nb_news = contributions_news.count() if contributions_news is not None else 0
        nb_commentaires = contributions_commentaires.count() if contributions_commentaires is not None else 0
        nb_votes_sondages = votes_sondages.count() if votes_sondages is not None else 0
        nb_votes_commentaires = votes_commentaires.count() if votes_commentaires is not None else 0

        return {
            'contributions': nb_news + nb_commentaires,
            'votes': nb_votes_sondages + nb_votes_commentaires,
            'commentaires': nb_commentaires,
        }


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = ('username', 'password', 'password2', 'email', 'first_name', 'last_name')

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password": "Passwords do not match."})
        return attrs

    def create(self, validated_data):
        validated_data.pop('password2')
        user = User.objects.create_user(**validated_data)
        return user

class IdentifiantRegisterSerializer(serializers.Serializer):
    """
    Inscription simplifiée : un SEUL identifiant (email OU numéro de
    téléphone, détecté automatiquement selon sa forme -- voir
    users/api/v1/services.py:is_email) + un mot de passe. Remplace
    UserCreateSerializer pour RegisterView (POST /token/v1/register/) --
    UserCreateSerializer reste utilisé tel quel par UserViewSet.create
    (création par un superuser depuis l'admin, avec username/nom/prénom
    explicites), un usage différent qui n'a pas à changer ici.

    Crée désormais TOUJOURS le compte dans le schéma public (identité
    globale) -- voir RegisterView (token_manager/api/v1/views.py), qui
    se charge ensuite de l'adhésion au tenant courant.
    """
    identifiant = serializers.CharField(required=True, write_only=True)
    password = serializers.CharField(required=True, write_only=True, validators=[validate_password])

    def validate_identifiant(self, value):
        value = normaliser_identifiant(value)
        if not value:
            raise serializers.ValidationError("L'identifiant (email ou numéro de téléphone) est requis.")
        if not is_email(value) and not is_telephone_valide(value):
            raise serializers.ValidationError(
                "Entrez un email valide ou un numéro de téléphone valide (9 à 15 chiffres)."
            )
        return value

    def validate(self, attrs):
        if UsersService.get_user_by_identifiant(attrs['identifiant']) is not None:
            raise serializers.ValidationError({'identifiant': "Un compte existe déjà avec cet identifiant."})
        return attrs

    def create(self, validated_data):
        return UsersService.creer_utilisateur_depuis_identifiant(
            validated_data['identifiant'], validated_data['password'],
        )


class UserUpdateSerializer(serializers.ModelSerializer):
    """
    Édition d'un compte GLOBAL (identité uniquement). Rôle/organisation/
    établissement se gèrent désormais via `MembreTenantRoleUpdateSerializer`
    (adhesions/api/v1/serializers.py), dans le tenant concerné. Le mot de
    passe reste HORS de ce serializer — voir `change_password` (action
    dédiée, UserViewSet), jamais mêlé à une édition de profil.
    """

    class Meta:
        model = User
        fields = (
            'email', 'first_name', 'last_name', 'is_active', 'is_verified',
            'phone_number', 'address', 'date_of_birth',
        )

class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, validators=[validate_password])
    new_password2 = serializers.CharField(required=True)

    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password2']:
            raise serializers.ValidationError({"new_password": "Passwords do not match."})
        return attrs

class SuperUserCreateSerializer(UserCreateSerializer):
    def create(self, validated_data):
        validated_data.pop('password2')
        user = User.objects.create_superuser(**validated_data)
        return user
