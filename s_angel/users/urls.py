from django.urls import path

from . import views

app_name = "users"
urlpatterns = [
    path('', views.main, name='main'),
    path('signup/', views.signup, name='signup'),
    path('profile/update/', views.profile_update, name='profile_update'),
]
