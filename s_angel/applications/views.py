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
from .models import Transaction
from django.db.models import Sum
import openpyxl
from django.http import HttpResponse


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


# applications/views.py

@staff_member_required
def accounting_list(request):
    """회계 내역 목록 및 총액 계산 (나중에 넣은 것이 아래로 가도록 정렬 수정)"""
    
    # order_by에서 '-'를 제거하여 오름차순(과거->최신)으로 변경합니다.
    transactions = Transaction.objects.all().order_by('date', 'id')
    
    # 총 수입/지출 계산 (이 부분은 기존과 동일)
    total_income = transactions.filter(transaction_type='INCOME').aggregate(Sum('amount'))['amount__sum'] or 0
    total_expense = transactions.filter(transaction_type='EXPENSE').aggregate(Sum('amount'))['amount__sum'] or 0
    balance = total_income - total_expense

    context = {
        'transactions': transactions,
        'total_income': total_income,
        'total_expense': total_expense,
        'balance': balance,
    }
    return render(request, 'applications/accounting_list.html', context)

@staff_member_required
def accounting_create(request):
    if request.method == 'POST':
        # 리스트 형식으로 넘어오는 데이터를 처리
        dates = request.POST.getlist('date[]')
        item_names = request.POST.getlist('item_name[]')
        amounts = request.POST.getlist('amount[]')
        categories = request.POST.getlist('category[]')
        types = request.POST.getlist('transaction_type[]')
        descriptions = request.POST.getlist('description[]')

        transactions_to_create = []
        for i in range(len(item_names)):
            if item_names[i]: # 항목명이 있는 경우에만 생성
                transactions_to_create.append(Transaction(
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
        
        return redirect('applications:accounting_list')
    
    return render(request, 'applications/accounting_form.html')

@staff_member_required
def export_accounting_excel(request):
    """회계 내역을 엑셀로 내보내기"""
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="s_angel_회계록.xlsx"'

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "회계장부"

    # 헤더 작성
    headers = ['날짜', '항목명', '카테고리', '구분', '금액', '상세내용']
    ws.append(headers)

    # 데이터 작성
    transactions = Transaction.objects.all().order_by('-date')
    for tx in transactions:
        ws.append([
            tx.date.strftime('%Y-%m-%d'),
            tx.item_name,
            tx.category,
            tx.get_transaction_type_display(),
            tx.amount,
            tx.description
        ])

    wb.save(response)
    return response

@staff_member_required
def accounting_update(request, pk):
    """기존 회계 내역 수정"""
    transaction = get_object_or_404(Transaction, pk=pk)
    if request.method == 'POST':
        transaction.date = request.POST.get('date')
        transaction.item_name = request.POST.get('item_name')
        transaction.amount = request.POST.get('amount')
        transaction.category = request.POST.get('category')
        transaction.transaction_type = request.POST.get('transaction_type')
        transaction.description = request.POST.get('description')
        transaction.save()
        messages.success(request, "내역이 수정되었습니다.")
        return redirect('applications:accounting_list')
    
    return render(request, 'applications/accounting_update_form.html', {'transaction': transaction})

@staff_member_required
def accounting_delete(request, pk):
    """회계 내역 삭제"""
    if request.method == 'POST':
        transaction = get_object_or_404(Transaction, pk=pk)
        transaction.delete()
        messages.success(request, "내역이 삭제되었습니다.")
    return redirect('applications:accounting_list')