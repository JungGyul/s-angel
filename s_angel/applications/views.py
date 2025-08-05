# applications/views.py

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404
from .models import Event, Application
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import redirect
from .forms import EventCreateForm, UserGenderUpdateForm
import random
from django.contrib import messages
import datetime
from django.contrib.auth import get_user_model # <--- User를 직접 import하는 대신 이 함수를 가져옵니다.
User = get_user_model() # <--- settings.py에 설정된 User 모델을 가져와 변수에 할당합니다.
from django.db.models import Q


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

def _perform_tiered_lottery(applicants_qs, slots_to_fill):
    """우선 선발 및 경쟁 추첨을 수행하는 도우미 함수"""
    
    # QuerySet을 리스트로 변환하여 작업 (DB 재조회 방지)
    applicants_list = list(applicants_qs)

    if not applicants_list or slots_to_fill <= 0:
        return []

    # 1. 지원자를 두 그룹으로 나눕니다.
    priority_applicants = [app for app in applicants_list if app.participant.weight >= 3]
    regular_applicants = [app for app in applicants_list if app.participant.weight < 3]

    # 2. 우선 선발 그룹을 정렬합니다.
    random.shuffle(priority_applicants) # 동일 가중치 내 무작위성 보장
    priority_applicants.sort(key=lambda app: app.participant.weight, reverse=True) # 가중치 높은 순

    winners = []
    slots_remaining = slots_to_fill

    # 3. 우선 선발 그룹에서 당첨자를 먼저 확정합니다.
    num_priority_to_select = min(slots_remaining, len(priority_applicants))
    if num_priority_to_select > 0:
        priority_winners = priority_applicants[:num_priority_to_select]
        winners.extend(priority_winners)
        slots_remaining -= len(priority_winners)

    # 4. 남은 T/O가 있다면, 나머지 인원으로 경쟁 추첨을 진행합니다.
    remaining_applicants = priority_applicants[num_priority_to_select:] + regular_applicants
    
    if slots_remaining > 0 and remaining_applicants:
        remaining_weights = [app.participant.weight for app in remaining_applicants]
        num_regular_to_select = min(slots_remaining, len(remaining_applicants))
        
        regular_winners = random.choices(
            population=remaining_applicants,
            weights=remaining_weights,
            k=num_regular_to_select
        )
        winners.extend(regular_winners)
        
    return winners


@staff_member_required
def draw_event(request, event_id):
    """추첨 실행 뷰 (성비 맞춤 + 우선선발 로직 결합)"""
    event = get_object_or_404(Event, id=event_id)

    if Application.objects.filter(event=event, selected=True).exists():
        messages.info(request, "이미 추첨이 완료된 이벤트입니다.")
        return redirect('applications:dashboard')

    all_applicants = Application.objects.filter(event=event).select_related('participant')

    if not all_applicants.exists():
        messages.info(request, "지원자가 없어 추첨을 진행할 수 없습니다.")
        return redirect('applications:dashboard')

    winners = []
    # 1. 이벤트에 성비 인원이 설정되었는지 확인
    if event.male_slots > 0 or event.female_slots > 0:
        # --- 성비 맞춤 추첨 ---
        male_applicants = all_applicants.filter(participant__gender='M')
        female_applicants = all_applicants.filter(participant__gender='F')

        male_winners = _perform_tiered_lottery(male_applicants, event.male_slots)
        female_winners = _perform_tiered_lottery(female_applicants, event.female_slots)
        
        winners.extend(male_winners)
        winners.extend(female_winners)
    
    else:
        # --- 성비 없는 전체 추첨 ---
        winners = _perform_tiered_lottery(all_applicants, event.total_slots)

    if winners:
        # 당첨/탈락자 처리 로직은 기존과 동일
        selected_ids = [winner.id for winner in winners]
        Application.objects.filter(id__in=selected_ids).update(selected=True)

        winner_user_ids = [winner.participant.id for winner in winners]
        User.objects.filter(id__in=winner_user_ids).update(weight=1)

        from django.db.models import F
        loser_user_ids = Application.objects.filter(event=event, selected=False).values_list('participant_id', flat=True)
        User.objects.filter(id__in=loser_user_ids).update(weight=F('weight') + 1)
        
        messages.success(request, f"'{event.title}' 이벤트 추첨이 완료되었습니다.")
    else:
        messages.info(request, "추첨 조건에 맞는 지원자가 없어 당첨자를 선정하지 못했습니다.")

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

    # ▼▼▼ 검색 및 정렬 로직 시작 ▼▼▼

    # 1. GET 파라미터에서 검색어(q)를 가져옵니다.
    search_query = request.GET.get('q', None)

    # 2. 기본적으로 모든 활성 사용자를 가져옵니다.
    active_users = User.objects.filter(is_active=True).exclude(id=request.user.id)

    # 3. 만약 검색어가 있다면, 해당 검색어로 필터링합니다.
    if search_query:
        # username 필드 또는 name 필드에 검색어가 포함(icontains)된 사용자를 찾습니다.
        active_users = active_users.filter(
            Q(username__icontains=search_query) | Q(name__icontains=search_query)
        )

    # 4. 최종적으로 사용자 이름(name)을 기준으로 가나다순 정렬합니다.
    active_users = active_users.order_by('name')

    # ▲▲▲ 검색 및 정렬 로직 끝 ▲▲▲

    context = {
        'pending_users': pending_users,
        'active_users': active_users,
        'search_query': search_query, # 템플릿에 검색어를 전달
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

@staff_member_required
def reject_user(request, user_id):
    """선택한 사용자의 가입을 거절 (삭제)하는 뷰"""
    if request.method == 'POST':
        user_to_reject = get_object_or_404(User, id=user_id)
        username = user_to_reject.username
        user_to_reject.delete()
        messages.success(request, f"사용자 '{username}'의 가입 요청을 거절했습니다.")
    return redirect('applications:admin_page')
# applications/views.py 파일 하단에 추가

def introduction(request):
    """소개 페이지를 렌더링하는 뷰"""
    return render(request, 'applications/introduction.html')

@staff_member_required
def event_update(request, event_id):
    """기존 의전 활동을 수정하는 뷰"""
    event = get_object_or_404(Event, id=event_id)

    # ▼▼▼ 이 부분을 추가합니다 ▼▼▼
    # 추첨이 완료되었는지 확인
    is_drawn = Application.objects.filter(event=event, selected=True).exists()
    if is_drawn:
        messages.error(request, "이미 추첨이 완료된 활동은 수정할 수 없습니다.")
        return redirect('applications:dashboard')
    # ▲▲▲ 여기까지 ▲▲▲

    if request.method == 'POST':
        form = EventCreateForm(request.POST, instance=event)
        if form.is_valid():
            form.save()
            messages.success(request, f"'{event.title}' 활동이 성공적으로 수정되었습니다.")
            return redirect('applications:dashboard')
    else:
        form = EventCreateForm(instance=event)
        
    context = {
        'form': form,
        'event': event,
    }
    return render(request, 'applications/event_update.html', context)

@staff_member_required
def update_user_gender(request, user_id):
    """관리자가 사용자의 성별을 수정하는 뷰"""
    user_to_update = get_object_or_404(User, id=user_id)
    
    if request.method == 'POST':
        form = UserGenderUpdateForm(request.POST, instance=user_to_update)
        if form.is_valid():
            form.save()
            messages.success(request, f"'{user_to_update.name}' 님의 성별이 성공적으로 수정되었습니다.")
            return redirect('applications:admin_page')
    else:
        form = UserGenderUpdateForm(instance=user_to_update)
        
    context = {
        'form': form,
        'user_to_update': user_to_update,
    }
    return render(request, 'applications/update_user_gender.html', context)
