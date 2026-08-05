from django.urls import path

from .views import StatistiquesGlobalesView

urlpatterns = [
    path('globales/', StatistiquesGlobalesView.as_view(), name='statistiques-globales'),
]
