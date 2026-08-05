from django.urls import path, include

urlpatterns = [
    path('v1/', include('sondages.api.v1.urls')),
]
