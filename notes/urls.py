from django.urls import path

from . import views

urlpatterns = [
    path('', views.explore, name='note_explore'),
    path('me/', views.mine, name='my_notes'),
    path('me/saved/', views.saved_notes, name='my_saved_notes'),
    path('me/<uuid:note_id>/', views.my_note, name='my_note'),
    path('me/<uuid:note_id>/resources/', views.resources, name='my_note_resources'),
    path('me/<uuid:note_id>/pdf/', views.my_pdf, name='my_note_pdf'),
    path('me/<uuid:note_id>/publish/', views.publish, name='my_note_publish'),
    path('me/<uuid:note_id>/archive/', views.archive, name='my_note_archive'),
    path('<uuid:note_id>/', views.note_detail, name='note_detail'),
    path('<uuid:note_id>/pdf/', views.pdf, name='note_pdf'),
    path('<uuid:note_id>/like/', views.like, name='note_like'),
    path('<uuid:note_id>/save/', views.save, name='note_save'),
    path('<uuid:note_id>/comments/', views.comment_collection, name='note_comments'),
    path('<uuid:note_id>/comments/<uuid:comment_id>/', views.comment_detail, name='note_comment'),
]
