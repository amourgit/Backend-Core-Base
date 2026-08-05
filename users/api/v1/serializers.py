from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'is_active', 'date_joined')
        read_only_fields = ('id', 'date_joined')


class BadgeSerializer(serializers.ModelSerializer):
    class Meta:
        from users.models import Badge
        model = Badge
        fields = ('id', 'nom', 'icone', 'description')


class UtilisateurPublicSerializer(serializers.ModelSerializer):
    """
    Profil utilisateur public tel que consommé par le frontend — voir
    `Utilisateur` dans src/types/models/user.types.ts. Les identifiants
    numériques Django sont exposés en tant que chaînes (`id`) pour
    correspondre au contrat frontend, qui traite tous les identifiants
    comme des chaînes de façon uniforme.
    """
    id = serializers.CharField(source='pk', read_only=True)
    nom_affiche = serializers.SerializerMethodField()
    avatar = serializers.SerializerMethodField()
    badges = BadgeSerializer(many=True, read_only=True)
    etablissement = serializers.CharField(source='etablissement.nom', read_only=True, default=None)
    stats = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'username', 'nom_affiche', 'avatar', 'role', 'etablissement', 'email', 'badges', 'stats')

    def get_nom_affiche(self, obj):
        full_name = obj.get_full_name()
        return full_name if full_name != obj.username else obj.username

    def get_avatar(self, obj):
        if obj.profile_picture:
            request = self.context.get('request')
            url = obj.profile_picture.url
            return request.build_absolute_uri(url) if request else url
        return None

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

class UserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('email', 'first_name', 'last_name')

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
