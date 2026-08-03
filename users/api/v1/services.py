from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import transaction

User = get_user_model()

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