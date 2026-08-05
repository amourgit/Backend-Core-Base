from django.urls import path, include

urlpatterns = [
    path('v1/', include('referentiels.api.v1.urls')),
]
