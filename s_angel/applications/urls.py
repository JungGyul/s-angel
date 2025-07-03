from django.urls import path
from . import views

app_name = "applications"  # ✅ 이 줄이 꼭 있어야 namespace 사용 가능


urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('create/', views.create_event, name='create_event'),
    path('apply/<int:event_id>/', views.apply_event, name='apply_event'),
    path('draw/<int:event_id>/', views.draw_event, name='draw_event'),
    path('statistics/', views.event_statistics, name='event_statistics'),
    path('winners/<int:event_id>/', views.event_winners, name='event_winners'),
    path('delete/<int:event_id>/', views.delete_event, name='delete_event'),
    path('event/<int:event_id>/cancel/', views.cancel_application, name='cancel_event'),

    path('admin-page/', views.admin_page, name='admin_page'),
    path('user/<int:user_id>/approve/', views.approve_user, name='approve_user'),
    path('user/<int:user_id>/delete/', views.delete_user, name='delete_user'),
    path('user/<int:user_id>/update_weight/', views.update_user_weight, name='update_user_weight'),
    path('user/<int:user_id>/reject/', views.reject_user, name='reject_user'),
]