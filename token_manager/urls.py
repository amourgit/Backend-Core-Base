from django.urls import path, include

urlpatterns = [
    # Routes d'api par version
    path('v1/', include('token_manager.api.v1.urls')),
]
