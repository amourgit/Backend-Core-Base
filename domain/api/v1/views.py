from django.shortcuts import render
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from domain.models import Domain
from .serializers import DomainSerializer
from token_manager.api.v1.permissions import IsAccessTokenTenant


# Create your views here.
class DomainViewSet(viewsets.ModelViewSet):
    queryset = Domain.objects.all()
    serializer_class = DomainSerializer
    permission_classes = [IsAccessTokenTenant, IsAuthenticated]