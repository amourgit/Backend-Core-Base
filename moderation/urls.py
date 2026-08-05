from django.urls import path, include

urlpatterns = [
    path('v1/', include('moderation.api.v1.urls')),
]
