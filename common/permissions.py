"""
common/permissions.py
=======================

Permissions DRF réutilisables par toutes les apps métier, basées sur
`User.role` (voir users/models.py). Centralisées ici pour éviter de
dupliquer la même logique de contrôle d'accès dans chaque app.
"""

from rest_framework.permissions import SAFE_METHODS, BasePermission

ROLES_MODERATION = ('moderateur', 'administrateur')


def a_role(user, *roles):
    if not (user and user.is_authenticated):
        return False
    if user.is_superuser:
        return True
    return getattr(user, 'role', None) in roles


class EstModerateurOuAdmin(BasePermission):
    """Accès réservé aux modérateurs et administrateurs (ou superuser Django)."""

    def has_permission(self, request, view):
        return a_role(request.user, *ROLES_MODERATION)


class LectureLibreEcritureAuthentifie(BasePermission):
    """Lecture publique (y compris anonyme), écriture réservée aux utilisateurs connectés."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_authenticated)


class LectureLibreEcritureModerateur(BasePermission):
    """Lecture publique, écriture réservée aux modérateurs/administrateurs
    (référentiels peu volatils : catégories, organisations, établissements)."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return a_role(request.user, *ROLES_MODERATION)


class EstProprietaireOuModerateurOuLectureSeule(BasePermission):
    """Lecture publique. Écriture : le propriétaire de la ressource
    (`obj.auteur == request.user`), ou un modérateur/administrateur."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        if a_role(request.user, *ROLES_MODERATION):
            return True
        auteur = getattr(obj, 'auteur', None)
        return auteur is not None and auteur_id_matches(auteur, request.user)


def auteur_id_matches(auteur, user):
    return getattr(auteur, 'pk', auteur) == getattr(user, 'pk', user)
