from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from ... import models
from .permissions import NotificationPermission
from .serializers import NotificationSerializer


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    - GET  /notifications/v1/notifications/
    - POST /notifications/v1/notifications/{id}/read/
    - POST /notifications/v1/notifications/read-all/
    """
    serializer_class = NotificationSerializer
    permission_classes = [NotificationPermission]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['lu', 'format', 'category_tab', 'urgente']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return models.Notification.objects.none()
        return models.Notification.objects.actifs().filter(destinataire=self.request.user).order_by('-cree_le')

    @action(detail=True, methods=['post'], url_path='read')
    def marquer_lu(self, request, pk=None):
        notification = self.get_object()
        if not notification.lu:
            notification.lu = True
            notification.save(update_fields=['lu'])
        return Response(NotificationSerializer(notification).data)

    @action(detail=False, methods=['post'], url_path='read-all')
    def marquer_tout_lu(self, request):
        self.get_queryset().filter(lu=False).update(lu=True)
        return Response({'detail': 'Toutes les notifications ont été marquées comme lues.'})
