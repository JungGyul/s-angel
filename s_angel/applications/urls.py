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

    path('introduction/', views.introduction, name='introduction'),
    # applications/urls.py 에 추가

    path('event/<int:event_id>/update/', views.event_update, name='event_update'),


    path('event/<int:event_id>/review/', views.review_winners, name='review_winners'),
    path('event/<int:event_id>/finalize/', views.finalize_event, name='finalize_event'),

    # 회계 메인 (접속 시 현재 연도로 리다이렉트하거나 현재 연도 보여주기)
    path('accounting/', views.accounting_main, name='accounting_main'), 
    path('accounting/<int:year>/', views.accounting_list, name='accounting_year_list'),
    
    # 행사 세부 내역 (행사 클릭 시 이동)
    path('accounting/event/<int:event_id>/', views.event_detail, name='accounting_event_detail'),
    
    path('accounting/event/add/', views.event_create, name='event_create'), # 이 줄이 추가되어야 '새 행사 만들기'가 작동해요!
    path('accounting/api/events/', views.accounting_events_api, name='accounting_events_api'),

    # 생성/수정/삭제
    path('accounting/add/', views.accounting_create, name='accounting_create'),
    path('accounting/export/<int:year>/', views.export_accounting_excel, name='export_accounting_excel'),
    path('accounting/<int:pk>/update/', views.accounting_update, name='accounting_update'),
    path('accounting/<int:pk>/delete/', views.accounting_delete, name='accounting_delete'),

    path('accounting/event/<int:pk>/update/', views.accounting_event_update, name='accounting_event_update'),
    path('accounting/event/<int:pk>/delete/', views.accounting_event_delete, name='accounting_event_delete'),


    path('user/<int:user_id>/update_info/', views.update_user_info, name='update_user_info'),

    path('admin/budget-year/create/', views.create_budget_year, name='create_budget_year'),
    path('admin/accounting/initialize/', views.initialize_accounting_data, name='initialize_accounting_data'),
    
    # 회계 열람 권한 토글
    path('user/<int:user_id>/toggle_permission/', views.toggle_accounting_permission, name='toggle_accounting_permission'),
    path("calendar/", views.calendar_view, name="calendar"),
    path("calendar/add/", views.add_schedule, name="add_schedule"),
    path("calendar/update/<int:pk>/", views.update_schedule, name="update_schedule"),
    path("calendar/delete/<int:pk>/", views.delete_schedule, name="delete_schedule"),

]