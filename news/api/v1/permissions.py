"""
news/api/v1/permissions.py
=============================

Miroir côté backend du catalogue de permissions frontend
(src/lib/permissions/rolePermissions.ts) : défense en profondeur — le
frontend masque déjà l'UI, mais l'API ne fait jamais confiance au seul
client pour appliquer les règles d'autorisation.
"""

from rest_framework.permissions import SAFE_METHODS, BasePermission

from common.permissions import a_role, ROLES_MODERATION

ROLES_PEUVENT_CREER_NEWS = ('organisation',) + ROLES_MODERATION


class NewsPermission(BasePermission):
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        if view.action == 'create':
            return a_role(request.user, *ROLES_PEUVENT_CREER_NEWS)
        # react : autorisé pour tous (anonymes inclus)
        if view.action == 'reagir':
            return True
        # partager : tout utilisateur authentifié
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        if view.action == 'reagir':
            return True
        if a_role(request.user, *ROLES_MODERATION):
            return True
        return obj.auteur_id == request.user.id


class NewsSousRessourcePermission(BasePermission):
    """Permission des sous-collections d'une News (médias, galerie,
    documents joints) — même politique que `NewsPermission` sur la News
    parente elle-même : lecture publique, écriture réservée à
    l'auteur de la News rattachée ou à un modérateur/administrateur.
    Ces modèles (NewsMedia, NewsImageGalerie, DocumentJoint) ne portent
    pas le Socle de Traçabilité (pas de `cree_par`), l'appartenance se
    vérifie donc via `obj.news.auteur_id`."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        if a_role(request.user, *ROLES_MODERATION):
            return True
        return obj.news.auteur_id == request.user.id
