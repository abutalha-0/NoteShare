from django.urls import path

from . import views

urlpatterns = [
    path('<str:resource>/', views.collection, name='academic_collection'),
    path('<str:resource>/<uuid:item_id>/', views.detail, name='academic_detail'),
]
