# applications/views.py

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404
from .models import Event, Application
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import redirect
from .forms import EventCreateForm
import random
from django.contrib import messages
import datetime
from django.contrib.auth import get_user_model # <--- User를 직접 import하는 대신 이 함수를 가져옵니다.
User = get_user_model() # <--- settings.py에 설정된 User 모델을 가져와 변수에 할당합니다.

@login_required
def cancel_application(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    application = Application.objects.filter(event=event, participant=request.user).first()
    if not application:
        return redirect('applications:dashboard')

    # 이미 추첨이 완료된 경우 취소 불가
    if Application.objects.filter(event=event, selected=True).exists():
        return redirect('applications:dashboard')

    application.delete()
    return redirect('applications:dashboard')

@staff_member_required
def delete_event(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    event.delete()
    return redirect('applications:dashboard')

@login_required
def event_winners(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    winners = Application.objects.filter(event=event, selected=True)

    return render(request, 'applications/winners.html', {'event': event, 'winners': winners})

# applications/views.py의 event_statistics 함수

@staff_member_required
def event_statistics(request):
    events = Event.objects.all().order_by('-id')

    event_data = []
    for event in events:
        # ▼▼▼ 이 부분을 수정합니다 ▼▼▼
        # 'selected'를 기준으로 내림차순(True가 먼저), username을 기준으로 오름차순 정렬
        applications = Application.objects.filter(event=event).select_related('participant').order_by('-selected', 'participant__username')

        winners = applications.filter(selected=True)
        is_drawn = winners.exists()

        event_data.append({
            'event': event,
            'applications': applications,
            'winners': winners,
            'losers': applications.filter(selected=False),
            'total_applications': applications.count(),
            'male_applications': applications.filter(participant__gender='M').count(),
            'female_applications': applications.filter(participant__gender='F').count(),
            'total_selected': winners.count(),
            'is_drawn': is_drawn,
        })

    return render(request, 'applications/statistics.html', {'event_data': event_data})

@staff_member_required
def draw_event(request, event_id):
    """추첨 실행 뷰"""
    event = get_object_or_404(Event, id=event_id)

    if Application.objects.filter(event=event, selected=True).exists():
        messages.info(request, "이미 추첨이 완료된 이벤트입니다.")
        return redirect('applications:dashboard')

    all_applicants = Application.objects.filter(event=event).select_related('participant')

    if all_applicants.count() == 0:
        messages.info(request, "지원자가 없어 추첨을 진행할 수 없습니다.")
        return redirect('applications:dashboard')

    applicant_weights = [app.participant.weight for app in all_applicants]
    num_to_select = min(event.total_slots, all_applicants.count())

    if num_to_select > 0:
        winners = random.choices(
            population=list(all_applicants),
            weights=applicant_weights,
            k=num_to_select
        )

        # 1. 당첨된 '신청'의 상태를 업데이트합니다.
        selected_ids = [winner.id for winner in winners]
        Application.objects.filter(id__in=selected_ids).update(selected=True)

        # ▼▼▼ (여기 추가) 당첨된 '사용자'의 가중치를 1로 초기화합니다. ▼▼▼
        winner_user_ids = [winner.participant.id for winner in winners]
        User.objects.filter(id__in=winner_user_ids).update(weight=1)

        # 3. 떨어진 '사용자'의 가중치를 1씩 올립니다.
        from django.db.models import F
        loser_user_ids = Application.objects.filter(event=event, selected=False).values_list('participant_id', flat=True)
        User.objects.filter(id__in=loser_user_ids).update(weight=F('weight') + 1)
        
        messages.success(request, f"'{event.title}' 이벤트 추첨이 완료되었습니다.")
    else:
        messages.info(request, "뽑을 인원이 없어 추첨을 진행하지 않았습니다.")

    return redirect('applications:dashboard')


@login_required
def apply_event(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    today = datetime.date.today()

    if event.end_date < today or Application.objects.filter(event=event, participant=request.user).exists():
        return redirect('applications:dashboard')

    # ▼▼▼ 핵심 변경: 신청 시 가중치를 계산할 필요 없이, 그냥 신청 정보만 생성합니다 ▼▼▼
    Application.objects.create(
        event=event,
        participant=request.user
    )
    return redirect('applications:dashboard')


@staff_member_required
def create_event(request):
    if request.method == 'POST':
        form = EventCreateForm(request.POST)
        if form.is_valid():
            event = form.save(commit=False)  # 아직 저장하지 않고

            # 🔥 여기 추가!
            if event.male_slots is None:
                event.male_slots = 0
            if event.female_slots is None:
                event.female_slots = 0

            event.save()  # 이제 저장!
            return redirect('applications:dashboard')
    else:
        form = EventCreateForm()

    return render(request, 'applications/create_event.html', {'form': form})

@login_required
def dashboard(request):
    today = datetime.date.today()
    
    # is_admin 변수와 불필요한 if/else를 제거하여 코드를 단순화합니다.
    # 이벤트 목록은 관리자든 일반 사용자든 동일하게 가져옵니다.
    events = Event.objects.order_by('-id')

    my_applications = Application.objects.filter(participant=request.user)
    applied_event_ids = my_applications.values_list('event_id', flat=True)

    event_status_list = []
    for event in events:
        is_drawn = Application.objects.filter(event=event, selected=True).exists()
        event_status_list.append({
            'event': event,
            'is_drawn': is_drawn,
        })

    context = {
        'event_status_list': event_status_list,
        'my_applications': my_applications,
        'applied_event_ids': applied_event_ids,
        'today': today,
    }

    return render(request, 'applications/dashboard.html', context)

# applications/views.py 의 admin_page 함수

@staff_member_required
def admin_page(request):
    """관리자 전용 종합 관리 페이지 뷰"""
    pending_users = User.objects.filter(is_active=False).order_by('-date_joined')
    
    # ▼▼▼ 이 부분을 수정합니다 ▼▼▼
    # 활성 사용자 목록에서, 현재 로그인한 사용자(request.user)는 제외합니다.
    active_users = User.objects.filter(is_active=True).exclude(id=request.user.id).order_by('-date_joined')

    context = {
        'pending_users': pending_users,
        'active_users': active_users,
    }
    return render(request, 'applications/admin_page.html', context)


@staff_member_required
def approve_user(request, user_id):
    """선택한 사용자를 활성화(가입 승인)하는 뷰"""
    if request.method == 'POST':
        user_to_approve = get_object_or_404(User, id=user_id)
        user_to_approve.is_active = True
        user_to_approve.save()
        messages.success(request, f"사용자 '{user_to_approve.username}'의 가입을 승인했습니다.")
    return redirect('applications:admin_page')

@staff_member_required
def update_user_weight(request, user_id):
    """관리자가 사용자의 누적 가중치를 수정하는 요청을 처리"""
    if request.method == 'POST':
        user_to_update = get_object_or_404(User, id=user_id)
        new_weight = int(request.POST.get('weight'))
        if new_weight >= 1:
            user_to_update.weight = new_weight
            user_to_update.save()
            messages.success(request, f"{user_to_update.username}님의 누적 가중치가 {new_weight}(으)로 수정되었습니다.")
        else:
            messages.error(request, "가중치는 1 이상이어야 합니다.")
    return redirect('applications:admin_page')

@staff_member_required
def delete_user(request, user_id):
    """관리자가 사용자를 삭제하는 요청을 처리"""
    if request.method == 'POST':
        if request.user.id == user_id:
            messages.error(request, "자기 자신의 계정은 삭제할 수 없습니다.")
            return redirect('applications:admin_page')

        user_to_delete = get_object_or_404(User, id=user_id)
        username = user_to_delete.username
        user_to_delete.delete()
        messages.success(request, f"사용자 '{username}'이(가) 성공적으로 삭제되었습니다.")
    return redirect('applications:admin_page')