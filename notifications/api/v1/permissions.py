from rest_framework.permissions import BasePermission


class NotificationPermission(BasePermission):
    """Chaque utilisateur ne voit et ne gère que ses propres notifications."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        return obj.destinataire_id == request.user.id
