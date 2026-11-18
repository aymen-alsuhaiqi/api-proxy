from django.urls import path
from .views import proxy_view

urlpatterns = [
    path('proxy/', proxy_view, name='proxy'),
]
