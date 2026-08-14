import re
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.utils import timezone
from django.db import transaction

User = get_user_model()

# Même regex que User.clean() (users/models.py) -- délibérément dupliquée
# ici plutôt qu'importée : `clean()` valide un phone_number déjà affecté
# à l'instance, alors qu'ici on teste une chaîne brute AVANT de savoir si
# c'est un email ou un téléphone. Les deux DOIVENT rester en phase ; toute
# modification de l'un doit être répercutée sur l'autre.
TELEPHONE_REGEX = re.compile(r'^\+?1?\d{9,15}$')


def is_email(identifiant: str) -> bool:
    """True si `identifiant` est un email syntaxiquement valide (validateur
    Django standard -- plus robuste qu'une regex maison)."""
    try:
        validate_email((identifiant or '').strip())
        return True
    except DjangoValidationError:
        return False


def is_telephone_valide(identifiant: str) -> bool:
    return bool(TELEPHONE_REGEX.match((identifiant or '').strip()))


def normaliser_telephone(valeur: str) -> str:
    """Ne garde que les chiffres et un éventuel '+' initial -- deux saisies
    visuellement différentes ('074 12 34 56' / '074-12-34-56') doivent
    désigner le MÊME identifiant de connexion à la recherche comme à la
    création."""
    valeur = (valeur or '').strip()
    signe = '+' if valeur.startswith('+') else ''
    chiffres = re.sub(r'\D', '', valeur)
    return f"{signe}{chiffres}"


def normaliser_identifiant(identifiant: str) -> str:
    """Point d'entrée UNIQUE de normalisation d'un identifiant de connexion
    (email OU téléphone) -- utilisé à la fois à la recherche
    (get_user_by_identifiant) et à la création
    (creer_utilisateur_depuis_identifiant), pour que les deux ne puissent
    jamais diverger sur ce qu'est "le même" identifiant."""
    identifiant = (identifiant or '').strip()
    if is_email(identifiant):
        return identifiant.lower()
    return normaliser_telephone(identifiant)


class UsersService:
    """
    Service utilitaire pour la gestion des utilisateurs.
    """

    @staticmethod
    def create_user(username, email, password=None, **extra_fields):
        """Crée un nouvel utilisateur actif."""
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            is_active=True,
            date_joined=timezone.now(),
            **extra_fields
        )
        return user

    @staticmethod
    def get_user_by_id(user_id):
        return User.objects.filter(id=user_id).first()

    @staticmethod
    def get_user_by_username(username):
        return User.objects.filter(username=username).first()

    @staticmethod
    def get_user_by_email(email):
        return User.objects.filter(email=email).first()

    @staticmethod
    def list_active_users():
        return User.objects.filter(is_active=True)

    @staticmethod
    def list_all_users():
        return User.objects.all()

    @staticmethod
    def activate_user(user_id):
        user = UsersService.get_user_by_id(user_id)
        if user and not user.is_active:
            user.is_active = True
            user.save(update_fields=['is_active'])
        return user

    @staticmethod
    def deactivate_user(user_id):
        user = UsersService.get_user_by_id(user_id)
        if user and user.is_active:
            user.is_active = False
            user.save(update_fields=['is_active'])
        return user

    @staticmethod
    def update_user(user_id, **fields):
        user = UsersService.get_user_by_id(user_id)
        if user:
            for key, value in fields.items():
                setattr(user, key, value)
            user.save()
        return user

    @staticmethod
    def delete_user(user_id):
        user = UsersService.get_user_by_id(user_id)
        if user:
            user.delete()
            return True
        return False

    @staticmethod
    def exists_by_username(username):
        return User.objects.filter(username=username).exists()

    @staticmethod
    def get_user_by_identifiant(identifiant):
        """
        Cherche un utilisateur par email OU par numéro de téléphone --
        SEULS identifiants de connexion exposés côté frontend (un unique
        champ "identifiant" sur LoginPage/RegisterPage, voir la demande
        produit : connexion/inscription simplifiées). La forme de la
        chaîne (email vs téléphone) détermine seule le champ interrogé --
        voir normaliser_identifiant()/is_email().

        Retourne None si aucun compte ne correspond (permet à
        CustomTokenObtainPairView de distinguer "compte inexistant"
        de "mot de passe incorrect").
        """
        identifiant = normaliser_identifiant(identifiant)
        if not identifiant:
            return None
        if is_email(identifiant):
            return User.objects.filter(email__iexact=identifiant).first()
        return User.objects.filter(phone_number=identifiant).first()

    @staticmethod
    def generer_username_depuis_identifiant(identifiant):
        """
        Dérive un username unique et valide (règles UnicodeUsernameValidator
        de Django : lettres/chiffres/@/./+/-/_) à partir d'un identifiant de
        connexion (email ou téléphone). Le username reste un champ interne
        requis par AbstractUser -- il n'est plus jamais saisi ni affiché à
        l'utilisateur dans ce flux d'inscription simplifié.
        """
        identifiant = normaliser_identifiant(identifiant)
        base = identifiant.split('@')[0] if is_email(identifiant) else identifiant.lstrip('+')
        base = re.sub(r'[^\w.@+-]', '', base) or 'membre'
        base = base[:140]  # marge pour le suffixe de désambiguïsation ci-dessous (max_length=150)

        username = base
        suffixe = 1
        while User.objects.filter(username=username).exists():
            suffixe += 1
            username = f"{base}{suffixe}"
        return username

    @staticmethod
    @transaction.atomic
    def creer_utilisateur_depuis_identifiant(identifiant, password):
        """
        Inscription simplifiée : un SEUL identifiant (email OU téléphone)
        + mot de passe -- voir IdentifiantRegisterSerializer
        (users/api/v1/serializers.py). Utilisé aussi bien par
        RegisterView (inscription volontaire) que par
        CustomTokenObtainPairView lorsque l'utilisateur confirme vouloir
        créer un compte après un login sur un identifiant introuvable
        (voir token_manager/api/v1/views.py).
        """
        identifiant = normaliser_identifiant(identifiant)
        username = UsersService.generer_username_depuis_identifiant(identifiant)
        champs_contact = {'email': identifiant} if is_email(identifiant) else {'phone_number': identifiant}
        return User.objects.create_user(
            username=username,
            password=password,
            is_active=True,
            date_joined=timezone.now(),
            **champs_contact,
        )

    @staticmethod
    def exists_by_email(email):
        return User.objects.filter(email=email).exists()

    @staticmethod
    def exists_by_id(user_id):
        return User.objects.filter(id=user_id).exists()

    @staticmethod
    @transaction.atomic
    def bulk_deactivate_users(user_ids):
        return User.objects.filter(id__in=user_ids, is_active=True).update(is_active=False)

    @staticmethod
    @transaction.atomic
    def bulk_activate_users(user_ids):
        return User.objects.filter(id__in=user_ids, is_active=False).update(is_active=True) 