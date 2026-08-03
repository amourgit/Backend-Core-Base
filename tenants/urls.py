from django.urls import path, include

urlpatterns = [
    # Routes d'api par version
    path('v1/', include('tenants.api.v1.urls')),
]
