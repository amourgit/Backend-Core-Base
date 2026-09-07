from django.urls import path

from .views import MesStatistiquesView, StatistiquesGlobalesView

urlpatterns = [
    path('globales/', StatistiquesGlobalesView.as_view(), name='statistiques-globales'),
    path('moi/', MesStatistiquesView.as_view(), name='statistiques-moi'),
]
