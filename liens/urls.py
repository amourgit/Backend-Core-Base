from django.urls import path, include

urlpatterns = [
    path('v1/', include('liens.api.v1.urls')),
]
