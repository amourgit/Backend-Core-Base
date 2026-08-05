from django.urls import path, include

urlpatterns = [
    path('v1/', include('news.api.v1.urls')),
]
