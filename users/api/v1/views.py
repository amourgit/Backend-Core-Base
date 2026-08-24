from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from common.permissions import a_role, ROLES_MODERATION
from .serializers import (
    UserSerializer,
    UtilisateurPublicSerializer,
    UserCreateSerializer,
    UserUpdateSerializer,
    ChangePasswordSerializer
)

User = get_user_model()

class IsSuperUser(permissions.BasePermission):
    """
    Permission to allow only superusers.
    """
    def has_permission(self, request, view):
        return request.user and request.user.is_superuser


class EstModerateurOuAdministrateur(permissions.BasePermission):
    """Gestion des comptes (backoffice) réservée aux modérateurs et
    administrateurs — voir common.permissions.EstModerateurOuAdmin,
    dupliqué ici plutôt qu'importé pour ne pas coupler `users` (app la
    plus bas niveau du projet) à `common`, uniquement pour cette
    vérification triviale."""

    def has_permission(self, request, view):
        return a_role(request.user, *ROLES_MODERATION)

class UserViewSet(viewsets.ModelViewSet):
    """
    Endpoint d'ADMINISTRATION des comptes (backoffice) — distinct de
    `/users/v1/users/me/`, qui reste accessible à tout utilisateur
    authentifié pour lire SON PROPRE profil. `list`/`retrieve` exposent
    des champs sensibles (email, téléphone, adresse, rôle — voir
    UserSerializer) sur N'IMPORTE QUEL compte : réservés aux
    modérateurs/administrateurs, jamais à un simple utilisateur
    authentifié (c'était le cas avant ce changement, ce qui exposait au
    passage une élévation de privilège : n'importe quel compte pouvait
    PATCHer `role`/`is_active` de N'IMPORTE QUEL AUTRE compte).
    """
    queryset = User.objects.all().select_related('etablissement', 'organisation').prefetch_related('badges')
    serializer_class = UserSerializer
    permission_classes = [EstModerateurOuAdministrateur]

    def get_serializer_class(self):
        if self.action == 'create':
            return UserCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return UserUpdateSerializer
        return UserSerializer

    def get_permissions(self):
        if self.action == 'create':
            return [IsSuperUser()]
        if self.action in ('me', 'change_password'):
            # 'me' : profil de l'utilisateur courant, quel que soit son
            # rôle. 'change_password' : vérifie déjà l'ancien mot de
            # passe de l'objet ciblé (voir ci-dessous) -- pas de fuite
            # possible même ouvert à tout authentifié.
            return [permissions.IsAuthenticated()]
        return super().get_permissions()

    @action(detail=True, methods=['post'])
    def change_password(self, request, pk=None):
        user = self.get_object()
        serializer = ChangePasswordSerializer(data=request.data)
        
        if serializer.is_valid():
            if not user.check_password(serializer.validated_data['old_password']):
                return Response(
                    {"old_password": ["Incorrect password."]},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            user.set_password(serializer.validated_data['new_password'])
            user.save()
            return Response(
                {"message": "Password successfully changed."},
                status=status.HTTP_200_OK
            )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def me(self, request):
        serializer = UtilisateurPublicSerializer(request.user, context={'request': request})
        return Response(serializer.data)