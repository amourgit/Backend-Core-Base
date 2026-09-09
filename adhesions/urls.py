from django.urls import path, include

urlpatterns = [
    path('v1/', include('adhesions.api.v1.urls')),
]
