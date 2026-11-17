from django.urls import path

from . import views

urlpatterns = [
    path('me/', views.me, name='own_profile'),
    path('me/avatar/', views.my_avatar, name='own_profile_avatar'),
    path('<uuid:user_id>/', views.public, name='public_profile'),
    path('<uuid:user_id>/avatar/', views.public_avatar, name='public_profile_avatar'),
]
