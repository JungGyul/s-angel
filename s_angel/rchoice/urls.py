from django.urls import path
from . import views

app_name = "rchoice"  # ✅ 이 줄이 꼭 있어야 namespace 사용 가능


urlpatterns = [
    path('', views.dashboard, name='dashboard'),
]