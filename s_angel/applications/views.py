# applications/views.py

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404
from .models import Event, Application, BudgetYear, AccountingEvent
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import redirect
from .forms import EventCreateForm, UserInfoUpdateForm
import random
from django.contrib import messages
import datetime as dt
from django.contrib.auth import get_user_model # <--- User를 직접 import하는 대신 이 함수를 가져옵니다.
User = get_user_model() # <--- settings.py에 설정된 User 모델을 가져와 변수에 할당합니다.
from django.db.models import Q
from .models import Transaction, ClubSchedule
from django.db.models import Sum
import openpyxl
from django.http import HttpResponse
import json
from django.core.serializers.json import DjangoJSONEncoder
# applications/views.py 맨 위에 추가

from django.views.decorators.http import require_POST  # 👈 이 줄이 빠져서 에러가 났습니다!
from django.http import JsonResponse # AJAX 처리를 위해 이것도 필요합니다.
from datetime import date, timedelta
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils import timezone
from itertools import chain
from django.db import transaction

from zoneinfo import ZoneInfo
KST = ZoneInfo("Asia/Seoul")
UTC = dt.timezone.utc
def _get_default_budget_year():
    """활성 기수 있으면 그거, 없으면 최신 year"""
    active = BudgetYear.objects.filter(is_active=True).order_by('-year').first()
    if active:
        return active
    return BudgetYear.objects.order_by('-year').first()




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
    
    # ▼▼▼ 수정: 최종 확정(is_finalized)이 안 된 경우 빈 목록을 보여주거나 메시지 처리 ▼▼▼
    if not event.is_finalized:
        winners = []
        # (선택 사항) 관리자가 아닌 유저가 들어왔을 때 메시지를 띄우고 싶다면 아래 주석 해제
        # if not request.user.is_staff:
        #     messages.info(request, "아직 당첨자 발표 전입니다.")
        #     return redirect('applications:dashboard')
    else:
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
    """(버그 수정) 우선 선발 및 경쟁 추첨을 수행하는 도우미 함수"""
    
    applicants_list = list(applicants_qs)

    if not applicants_list or slots_to_fill <= 0:
        return []

    priority_applicants = [app for app in applicants_list if app.participant.weight >= 3]
    regular_applicants = [app for app in applicants_list if app.participant.weight < 3]

    random.shuffle(priority_applicants)
    priority_applicants.sort(key=lambda app: app.participant.weight, reverse=True)

    winners = []
    slots_remaining = slots_to_fill

    num_priority_to_select = min(slots_remaining, len(priority_applicants))
    if num_priority_to_select > 0:
        priority_winners = priority_applicants[:num_priority_to_select]
        winners.extend(priority_winners)
        slots_remaining -= len(priority_winners)

    remaining_applicants = priority_applicants[num_priority_to_select:] + regular_applicants
    
    if slots_remaining > 0 and remaining_applicants:
        # ▼▼▼ 여기가 핵심 수정 부분입니다 ▼▼▼
        # random.choices는 중복 당첨을 허용하므로, 중복 없는 가중치 추첨 로직으로 변경합니다.
        num_regular_to_select = min(slots_remaining, len(remaining_applicants))
        
        # 가중치 추첨을 위해 인원과 가중치를 별도 리스트로 복사합니다.
        population = list(remaining_applicants)
        weights = [app.participant.weight for app in population]

        regular_winners = []
        # 뽑아야 하는 인원수만큼 반복합니다.
        for _ in range(num_regular_to_select):
            # 더 이상 뽑을 사람이 없으면 중단합니다.
            if not population:
                break
            
            # 1. 가중치 기반으로 1명을 뽑습니다.
            chosen_one = random.choices(population, weights=weights, k=1)[0]
            regular_winners.append(chosen_one)
            
            # 2. 뽑힌 사람을 다음 추첨 인원에서 제외합니다.
            chosen_index = population.index(chosen_one)
            population.pop(chosen_index)
            weights.pop(chosen_index)
            
        winners.extend(regular_winners)
        # ▲▲▲ 여기까지가 핵심 수정 부분입니다 ▲▲▲
        
    return winners


@staff_member_required
def draw_event(request, event_id):
    """[수정] 1단계: 임시 추첨 (가중치 업데이트 안함)"""
    event = get_object_or_404(Event, id=event_id)
    if event.is_finalized: # 최종 확정 필드 체크
        messages.info(request, "이미 확정된 활동입니다.")
        return redirect('applications:dashboard')

    all_applicants = Application.objects.filter(event=event).select_related('participant')
    all_applicants.update(selected=False) # 기존 당첨 정보 초기화

    winners = []
    if event.male_slots > 0 or event.female_slots > 0:
        # 성비 맞춤 로직 실행
        male_apps = all_applicants.filter(participant__gender='M')
        female_apps = all_applicants.filter(participant__gender='F')
        
        m_winners = _perform_tiered_lottery(male_apps, event.male_slots)
        f_winners = _perform_tiered_lottery(female_apps, event.female_slots)
        
        combined = m_winners + f_winners
        # 총 T/O가 성비 합보다 작을 경우를 대비해 최종 샘플링
        winners = random.sample(combined, min(len(combined), event.total_slots))
    else:
        # 성비 없는 전체 추첨 실행
        winners = _perform_tiered_lottery(all_applicants, event.total_slots)

    if winners:
        selected_ids = [w.id for w in winners]
        Application.objects.filter(id__in=selected_ids).update(selected=True)
        messages.success(request, "임시 추첨 결과가 생성되었습니다. 명단을 검토해주세요.")
    
    return redirect('applications:dashboard')

@staff_member_required
def review_winners(request, event_id):
    
    """2단계: 관리자가 명단을 확인하고 수동으로 변경하는 페이지"""
    event = get_object_or_404(Event, id=event_id)
    
    # 당첨자와 탈락자를 나누어 가져옴
    applicants = Application.objects.filter(event=event).select_related('participant').order_by('participant__name')
    
    if request.method == 'POST':
        # 체크박스 등으로 선택된 ID 목록을 가져와서 업데이트
        selected_ids = request.POST.getlist('selected_applicants')
        applicants.update(selected=False)
        Application.objects.filter(id__in=selected_ids).update(selected=True)
        return redirect('applications:review_winners', event_id=event.id)

    context = {
        'event': event,
        'applicants': applicants,
        'winners_count': applicants.filter(selected=True).count(),
    }
    return render(request, 'applications/review_winners.html', context)

# applications/views.py

# applications/views.py

@staff_member_required
def finalize_event(request, event_id):
    event = get_object_or_404(Event, id=event_id)

    if event.is_finalized:
        messages.warning(request, "이미 최종 확정된 활동입니다.")
        return redirect('applications:dashboard')

    if request.method == 'POST':
        selected_ids = request.POST.getlist('selected_applicants')
        winner_count = len(selected_ids)

        # ✅ 0명 선택은 절대 불가 (서버에서 강제)
        if winner_count == 0:
            messages.error(request, "최소 1명 이상 선택해야 최종 확정할 수 있습니다.")
            return redirect('applications:review_winners', event_id=event.id)

        # ✅ 목표 인원과 달라도 막지 않고 경고만
        if winner_count != event.total_slots:
            messages.warning(
                request,
                f"목표 인원({event.total_slots}명)과 다르게 확정됩니다. (선택: {winner_count}명)"
            )

        # 1) 마지막 명단대로 DB 업데이트
        Application.objects.filter(event=event).update(selected=False)
        Application.objects.filter(id__in=selected_ids).update(selected=True)

        # 2) 가중치 로직 실행
        winner_user_ids = Application.objects.filter(event=event, selected=True).values_list('participant_id', flat=True)
        User.objects.filter(id__in=winner_user_ids).update(weight=1)

        from django.db.models import F
        loser_user_ids = Application.objects.filter(event=event, selected=False).values_list('participant_id', flat=True)
        User.objects.filter(id__in=loser_user_ids).update(weight=F('weight') + 1)

        event.is_finalized = True
        event.save()

        messages.success(request, f"'{event.title}' 명단이 확정되었습니다.")
        return redirect('applications:dashboard')

    return redirect('applications:review_winners', event_id=event.id)


@login_required
def apply_event(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    today = dt.date.today()

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
    today = dt.date.today()
    
    # is_admin 변수와 불필요한 if/else를 제거하여 코드를 단순화합니다.
    # 이벤트 목록은 관리자든 일반 사용자든 동일하게 가져옵니다.
    events = Event.objects.order_by('-id')

    my_applications = Application.objects.filter(participant=request.user)
    applied_event_ids = my_applications.values_list('event_id', flat=True)

    event_status_list = []
    for event in events:
        # 1. 임시 당첨자가 한 명이라도 있는지 확인
        is_drawn = Application.objects.filter(event=event, selected=True).exists()
        # 2. 모델에 추가한 is_finalized 필드 확인
        is_finalized = event.is_finalized 
        
        event_status_list.append({
            'event': event,
            'is_drawn': is_drawn,
            'is_finalized': is_finalized,
        })

    context = {
        'event_status_list': event_status_list,
        'my_applications': my_applications,
        'applied_event_ids': applied_event_ids,
        'today': today,
    }

    return render(request, 'applications/dashboard.html', context)

# applications/views.py 의 admin_page 함수

# applications/views.py

@staff_member_required
def admin_page(request):
    """관리자 페이지: 검색 및 기수 필터링 기능 추가"""
    search_query = request.GET.get('q', '')
    gen_filter = request.GET.get('gen', '') # 기수 필터 파라미터

    active_users = User.objects.filter(is_active=True).exclude(id=request.user.id)

    # 1. 기수 필터링
    if gen_filter:
        active_users = active_users.filter(generation=gen_filter)

    # 2. 검색어 필터링
    if search_query:
        active_users = active_users.filter(
            Q(username__icontains=search_query) | Q(name__icontains=search_query)
        )

    # 3. 정렬 및 기수 목록 가져오기 (필터 드롭다운용)
    active_users = active_users.order_by('-generation', 'name')
    generations = User.objects.values_list('generation', flat=True).distinct().order_by('-generation')

    context = {
        'active_users': active_users,
        'search_query': search_query,
        'gen_filter': gen_filter,
        'generations': generations,
        'pending_users': User.objects.filter(is_active=False),
    }
    return render(request, 'applications/admin_page.html', context)

# 권한 토글 뷰 추가
@staff_member_required
def toggle_accounting_permission(request, user_id):
    if request.method == 'POST':
        target_user = get_object_or_404(User, id=user_id)
        target_user.can_view_accounting = not target_user.can_view_accounting
        target_user.save()
        status = "부여" if target_user.can_view_accounting else "회수"
        messages.success(request, f"{target_user.name}님의 회계 열람 권한이 {status}되었습니다.")
    return redirect(request.META.get('HTTP_REFERER', 'applications:admin_page'))

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

# applications/views.py

@staff_member_required
def update_user_info(request, user_id):
    """성별과 기수를 모두 수정하는 뷰"""
    user_to_update = get_object_or_404(User, id=user_id)
    
    if request.method == 'POST':
        # UserInfoUpdateForm으로 이름 변경 권장
        form = UserInfoUpdateForm(request.POST, instance=user_to_update)
        if form.is_valid():
            form.save()
            messages.success(request, f"'{user_to_update.name}'님의 정보(기수: {user_to_update.generation}기)가 수정되었습니다.")
            return redirect('applications:admin_page')
    else:
        form = UserInfoUpdateForm(instance=user_to_update)
        
    context = {
        'form': form,
        'user_to_update': user_to_update,
    }
    return render(request, 'applications/update_user_info.html', context)


# applications/views.py

# applications/views.py

# -----------------------------------------------------------
# 1. 회계 메인: 현재 활성화된 기수로 리다이렉트
# -----------------------------------------------------------
@login_required
def accounting_main(request):
    """/accounting/ 접속 시 가장 최신(혹은 활성) 연도로 이동"""
    active_year = BudgetYear.objects.filter(is_active=True).first()
    if not active_year:
        active_year = BudgetYear.objects.order_by('-year').first()
    
    if active_year:
        return redirect('applications:accounting_year_list', year=active_year.year)
    else:
        # 연도 데이터가 하나도 없을 때 처리
        return render(request, 'applications/unauthorized.html', {'message': '등록된 회계 연도가 없습니다.'})

# -----------------------------------------------------------
# 2. 통합 타임라인 리스트 (가장 핵심 로직)
# -----------------------------------------------------------
@login_required
def accounting_list(request, year):
    """해당 연도의 일반 내역 + 행사 요약을 시간순으로 병합하여 출력"""

    if not (request.user.is_staff or getattr(request.user, 'can_view_accounting', False)):
        return render(request, 'applications/unauthorized.html')

    budget_year = get_object_or_404(BudgetYear, year=year)

    generals = Transaction.objects.filter(budget_year=budget_year, event__isnull=True)
    events = AccountingEvent.objects.filter(budget_year=budget_year)

    timeline = sorted(
        chain(generals, events),
        key=lambda x: x.date,
        reverse=True
    )

    total_stats = Transaction.objects.filter(budget_year=budget_year).aggregate(
        income=Sum('amount', filter=Q(transaction_type='INCOME')),
        expense=Sum('amount', filter=Q(transaction_type='EXPENSE'))
    )

    income = total_stats['income'] or 0
    expense = total_stats['expense'] or 0

    # ✅ 버튼(칩)용: 현재 보고 있는 기수 + 그 이전 기수 1개
    # ✅ 버튼(칩)용: 최근(왼쪽) → 과거(오른쪽) 순서, 최대 3개
    next_year = BudgetYear.objects.filter(year__gt=budget_year.year).order_by('year').first()
    prev_year = BudgetYear.objects.filter(year__lt=budget_year.year).order_by('-year').first()

    year_buttons = []
    if next_year:
        year_buttons.append(next_year)   # 더 최근이 왼쪽
    year_buttons.append(budget_year)     # 현재
    if prev_year:
        year_buttons.append(prev_year)   # 더 과거가 오른쪽


    context = {
        'budget_year': budget_year,
        'all_years': BudgetYear.objects.all().order_by('-year'),  # 드롭다운은 전체 유지
        'year_buttons': year_buttons,                             # ✅ 칩은 2개만
        'timeline': timeline,
        'total_income': income,
        'total_expense': expense,
        'balance': income - expense,
        'is_admin': request.user.is_staff,
    }
    return render(request, 'applications/accounting_list.html', context)


# -----------------------------------------------------------
# 3. 행사 세부 내역 뷰
# -----------------------------------------------------------
@login_required
def event_detail(request, event_id):
    """특정 행사(예: 축제)를 클릭했을 때 그 안의 세부 영수증 목록 표시"""
    event = get_object_or_404(AccountingEvent, pk=event_id)
    transactions = event.transactions.all().order_by('date')
    
    summary = event.get_summary() # 모델에서 만든 합계 함수 활용

    return render(request, 'applications/accounting_event_detail.html', {
        'event': event,
        'transactions': transactions,
        'summary': summary,
        'is_admin': request.user.is_staff,
    })

# -----------------------------------------------------------
# 4. 내역 생성 (기수 및 행사 선택 기능 포함)
# -----------------------------------------------------------
@staff_member_required
def accounting_create(request):
    if request.method == 'POST':
        # 어떤 기수와 행사에 저장할지 ID를 가져옴
        year_id = request.POST.get('budget_year')
        event_id = request.POST.get('accounting_event')

        budget_year = get_object_or_404(BudgetYear, pk=year_id)
        event = AccountingEvent.objects.filter(pk=event_id).first() if event_id else None

        # 리스트 데이터 처리 (정결님의 기존 로직 유지)
        dates = request.POST.getlist('date[]')
        item_names = request.POST.getlist('item_name[]')
        amounts = request.POST.getlist('amount[]')
        categories = request.POST.getlist('category[]')
        types = request.POST.getlist('transaction_type[]')
        descriptions = request.POST.getlist('description[]')

        transactions_to_create = []
        for i in range(len(item_names)):
            if item_names[i]:
                transactions_to_create.append(Transaction(
                    budget_year=budget_year,
                    event=event,  # 행사 주머니에 쏙 넣기
                    date=dates[i],
                    item_name=item_names[i],
                    amount=amounts[i],
                    category=categories[i],
                    transaction_type=types[i],
                    description=descriptions[i]
                ))

        if transactions_to_create:
            Transaction.objects.bulk_create(transactions_to_create)
            messages.success(request, f"{len(transactions_to_create)}건의 내역이 추가되었습니다.")

        return redirect('applications:accounting_year_list', year=budget_year.year)

    # ✅ GET: 활성 기수를 기본으로 선택 + (행사 상세에서 넘어온 경우) 프리셀렉트
    default_year = _get_default_budget_year()

    # 행사 상세에서:
    # /accounting/create/?year_id=<BudgetYear.id>&event_id=<AccountingEvent.id>
    initial_year_id = request.GET.get('year_id') or (str(default_year.id) if default_year else "")
    initial_event_id = request.GET.get('event_id') or ""

    return render(request, 'applications/accounting_form.html', {
        'years': BudgetYear.objects.all().order_by('-year'),
        # events는 "전체"를 넘겨도 되지만, UX적으로는 기수별 AJAX 로딩이 더 좋음
        # 지금은 기존 유지하려면 넘겨도 됨:
        # 'events': AccountingEvent.objects.all(),

        # ✅ 템플릿/JS에서 초기 선택용으로 사용
        'initial_year_id': initial_year_id,
        'initial_event_id': initial_event_id,
    })

    
    # GET 요청 시: 연도와 행사 목록을 폼에 전달
    return render(request, 'applications/accounting_form.html', {
        'years': BudgetYear.objects.all(),
        'events': AccountingEvent.objects.all(),
    })

# -----------------------------------------------------------
# 5. 엑셀 내보내기 (기수별 분리)
# -----------------------------------------------------------
@staff_member_required
def export_accounting_excel(request, year):
    budget_year = get_object_or_404(BudgetYear, year=year)
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="S-Angel_{year}_Accounting.xlsx"'

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"{year}년 회계장부"

    # 헤더에 '행사명' 컬럼 추가
    headers = ['날짜', '행사명', '항목명', '카테고리', '구분', '금액', '상세내용']
    ws.append(headers)

    transactions = Transaction.objects.filter(budget_year=budget_year).order_by('date')
    for tx in transactions:
        ws.append([
            tx.date.strftime('%Y-%m-%d'),
            tx.event.name if tx.event else "일반",
            tx.item_name,
            tx.category,
            tx.get_transaction_type_display(),
            tx.amount,
            tx.description
        ])

    wb.save(response)
    return response

@staff_member_required
def event_create(request):
    """'축제', 'MT' 같은 행사 주머니를 생성하는 뷰"""
    if request.method == 'POST':
        year_id = request.POST.get('budget_year')
        name = request.POST.get('name')
        date = request.POST.get('date')

        budget_year = get_object_or_404(BudgetYear, pk=year_id)
        AccountingEvent.objects.create(
            budget_year=budget_year,
            name=name,
            date=date
        )
        return redirect('applications:accounting_year_list', year=budget_year.year)

    # ✅ GET: 활성 기수를 기본으로 선택
    default_year = _get_default_budget_year()

    return render(request, 'applications/event_form.html', {
        'years': BudgetYear.objects.all().order_by('-year'),
        'initial_year_id': str(default_year.id) if default_year else "",
    })

@staff_member_required
def accounting_update(request, pk):
    """기존 회계 내역 수정: 연도 및 행사 이동 로직 포함"""
    transaction = get_object_or_404(Transaction, pk=pk)
    
    if request.method == 'POST':
        # 1. 외래키(연도, 행사) 데이터 가져오기
        year_id = request.POST.get('budget_year')
        event_id = request.POST.get('accounting_event')

        # 2. 데이터 업데이트
        transaction.budget_year = get_object_or_404(BudgetYear, pk=year_id)
        # 행사는 '선택 안 함(일반 내역)'일 수 있으므로 filter().first() 처리
        transaction.event = AccountingEvent.objects.filter(pk=event_id).first() if event_id else None
        
        transaction.date = request.POST.get('date')
        transaction.item_name = request.POST.get('item_name')
        transaction.amount = request.POST.get('amount')
        transaction.category = request.POST.get('category')
        transaction.transaction_type = request.POST.get('transaction_type')
        transaction.description = request.POST.get('description')
        
        transaction.save()
        
        messages.success(request, f"'{transaction.item_name}' 내역이 수정되었습니다.")
        
        # 3. 중요: 수정된 내역이 속한 기수의 리스트 페이지로 리다이렉트
        return redirect('applications:accounting_year_list', year=transaction.budget_year.year)
    
    # GET 요청 시: 폼에 필요한 연도/행사 목록 함께 전달
    context = {
        'transaction': transaction,
        'years': BudgetYear.objects.all().order_by('-year'),
        'events': AccountingEvent.objects.filter(budget_year=transaction.budget_year) # 현재 기수 행사들
    }
    return render(request, 'applications/accounting_update_form.html', context)

# views.py 수정 제안
@staff_member_required
def accounting_delete(request, pk):
    """회계 내역 삭제: 삭제 후 원래 있던 연도 페이지로 유지"""
    if request.method == 'POST':
        transaction = get_object_or_404(Transaction, pk=pk)
        target_year = transaction.budget_year.year # 삭제 전 연도 저장
        transaction.delete()
        messages.success(request, "내역이 삭제되었습니다.")
        return redirect('applications:accounting_year_list', year=target_year) # 삭제 후 그 연도 장부로!
    return redirect('applications:accounting_list')

@staff_member_required
def accounting_events_api(request):
    """
    GET /accounting/api/events/?year_id=3
    -> 해당 BudgetYear(pk=3)의 행사 목록 반환
    """
    year_id = request.GET.get('year_id')
    if not year_id:
        return JsonResponse({'events': []})

    budget_year = get_object_or_404(BudgetYear, pk=year_id)

    events = AccountingEvent.objects.filter(budget_year=budget_year).order_by('-date', '-id')
    data = [{'id': e.id, 'name': e.name, 'date': e.date.strftime('%Y-%m-%d')} for e in events]
    return JsonResponse({'events': data})

#-----------------------------------------------------------일정관리------------------------------------------------
def _parse_iso_dt(s: str | None):
    if not s:
        return None
    try:
        d = dt.datetime.fromisoformat(s.replace('Z', '+00:00'))

        # timezone 없는 naive면 KST로 간주
        if timezone.is_naive(d):
            d = timezone.make_aware(d, KST)

        # DB 저장은 UTC로 (Django USE_TZ=True 표준)
        return d.astimezone(UTC)
    except Exception:
        return None



@login_required
@ensure_csrf_cookie
def calendar_view(request):
    schedules = ClubSchedule.objects.all().order_by("start_at")
    schedule_list = []

    for s in schedules:
        start_local = s.start_at.astimezone(KST)
        item = {
            "id": s.id,
            "title": s.title,
            "start": start_local.isoformat(),  # "…+09:00"
            "allDay": False,
            "color": s.color or "#1E3A8A",
            "extendedProps": {"content": s.content or ""},
        }
        if s.end_at:
            end_local = s.end_at.astimezone(KST)
            item["end"] = end_local.isoformat()

        schedule_list.append(item)

    context = {
        "schedules_json": json.dumps(schedule_list, cls=DjangoJSONEncoder),
        "is_admin": request.user.is_staff,
    }
    return render(request, "applications/calendar.html", context)



@staff_member_required
@require_POST
def add_schedule(request):
    try:
        data = json.loads(request.body.decode("utf-8"))

        start_at = _parse_iso_dt(data.get("start"))
        end_at = _parse_iso_dt(data.get("end"))

        if not start_at:
            return JsonResponse({"status": "error", "message": "시작 시간이 필요합니다."}, status=400)

        # end가 start보다 빠르거나 같으면 end 제거
        if end_at and end_at <= start_at:
            end_at = None

        ClubSchedule.objects.create(
            title=(data.get("title", "").strip() or "제목 없음"),
            start_at=start_at,
            end_at=end_at,
            content=data.get("content", "") or "",
            color=data.get("color", "#1E3A8A") or "#1E3A8A",
        )
        return JsonResponse({"status": "success"})

    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=400)


@staff_member_required
@require_POST
def update_schedule(request, pk):
    schedule = get_object_or_404(ClubSchedule, pk=pk)

    try:
        data = json.loads(request.body.decode("utf-8"))

        start_at = _parse_iso_dt(data.get("start")) or schedule.start_at
        end_at = _parse_iso_dt(data.get("end"))

        if end_at and end_at <= start_at:
            end_at = None

        schedule.title = (data.get("title", schedule.title).strip() or schedule.title)
        schedule.content = data.get("content", schedule.content or "") or ""
        schedule.start_at = start_at
        schedule.end_at = end_at
        schedule.color = data.get("color", schedule.color or "#1E3A8A") or "#1E3A8A"
        schedule.save()

        return JsonResponse({"status": "success"})

    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=400)

@staff_member_required
@require_POST
def delete_schedule(request, pk):
    schedule = get_object_or_404(ClubSchedule, pk=pk)
    schedule.delete()
    return JsonResponse({"status": "success"})

# -----------------------------------------------------------
# [관리자 전용] 1. 새 회계 연도(기수) 생성 및 활성화
# -----------------------------------------------------------
@staff_member_required
def create_budget_year(request):
    if request.method == 'POST':
        year_val = request.POST.get('year')
        
        if not year_val:
            messages.error(request, "연도를 입력해주세요.")
            return redirect('applications:admin_page')

        with transaction.atomic():
            # 1. 기존에 활성화된 모든 연도를 비활성화 (새 기수 집중을 위해)
            BudgetYear.objects.filter(is_active=True).update(is_active=False)
            
            # 2. 새 연도 생성 또는 업데이트 (이미 있으면 활성화만)
            budget_year, created = BudgetYear.objects.update_or_create(
                year=year_val,
                defaults={'is_active': True}
            )
            
        status_msg = "생성" if created else "활성화"
        messages.success(request, f"{year_val}년 회계 기수가 성공적으로 {status_msg}되었습니다.")
        return redirect('applications:admin_page')

    return redirect('applications:admin_page')

# -----------------------------------------------------------
# [관리자 전용] 2. 현재 활성 기수 데이터 전체 초기화
# -----------------------------------------------------------
@staff_member_required
def initialize_accounting_data(request):
    """현재 활성화된 기수의 모든 내역과 행사를 삭제"""
    if request.method == 'POST':
        active_year = BudgetYear.objects.filter(is_active=True).first()
        
        if active_year:
            # 1. 해당 연도에 속한 모든 내역(Transaction) 삭제
            # (AccountingEvent가 CASCADE 설정되어 있다면 내역부터 지워집니다)
            count_tx = active_year.all_transactions.count()
            count_event = active_year.events.count()
            
            active_year.all_transactions.all().delete()
            active_year.events.all().delete()
            
            messages.success(request, f"{active_year.year}년도의 내역 {count_tx}건과 행사 {count_event}건이 초기화되었습니다.")
        else:
            messages.error(request, "활성화된 회계 연도가 없어 초기화할 수 없습니다.")
            
        return redirect('applications:admin_page')
    
    return redirect('applications:admin_page')

