from django.urls import path, include

urlpatterns = [
    path('v1/', include('statistiques.api.v1.urls')),
]
