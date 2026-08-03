from django.urls import path, include

urlpatterns = [
    # Routes d'api par version
    path('v1/', include('users.api.v1.urls')),
]
