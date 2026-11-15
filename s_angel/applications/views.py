import datetime as dt
import json
import random
from itertools import chain
from zoneinfo import ZoneInfo

import openpyxl
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Count, Exists, F, OuterRef, Prefetch, Q, Sum
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from .accounting_forms import AccountingEventForm, AccountingTransactionForm
from .decorators import custom_staff_required as staff_member_required
from .forms import EventCreateForm, UserInfoUpdateForm
from .models import AccountingEvent, Application, BudgetYear, ClubSchedule, Event, Transaction, WeightChange

from .weight_service import attach_review_weights, calculate_draw_weights

User = get_user_model()
KST = ZoneInfo("Asia/Seoul")
UTC = dt.timezone.utc
def _get_default_budget_year():
    """활성 기수 있으면 그거, 없으면 최신 year"""
    active = BudgetYear.objects.filter(is_active=True).order_by('-year').first()
    if active:
        return active
    return BudgetYear.objects.order_by('-year').first()




def _application_action_response(
    request,
    *,
    event,
    applied,
    message,
    success=True,
):
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse(
            {
                "ok": success,
                "applied": applied,
                "event_id": event.pk,
                "event_title": event.title,
                "message": message,
            },
            status=200 if success else 409,
        )

    if success:
        messages.success(request, message)
    else:
        messages.warning(request, message)
    return redirect("applications:dashboard")


def _dashboard_event_action_response(
    request,
    *,
    event_id,
    event_title,
    action,
    message,
    success=True,
    **extra,
):
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        payload = {
            "ok": success,
            "action": action,
            "event_id": event_id,
            "event_title": event_title,
            "message": message,
        }
        payload.update(extra)
        return JsonResponse(
            payload,
            status=200 if success else 409,
        )

    if success:
        messages.success(request, message)
    else:
        messages.warning(request, message)
    return redirect("applications:dashboard")


@login_required
@require_POST
@transaction.atomic
def cancel_application(request, event_id):
    event = get_object_or_404(
        Event.objects.select_for_update(),
        id=event_id,
    )
    application = Application.objects.filter(event=event, participant=request.user).first()
    if not application:
        return _application_action_response(
            request,
            event=event,
            applied=False,
            message="이미 취소된 신청입니다.",
        )

    group_is_closed = (
        event.special_lottery_group
        and (
            event.special_lottery_group.is_drawn
            or event.special_lottery_group.is_finalized
        )
    )
    event_is_drawn = event.drawn_at is not None or Application.objects.filter(
        event=event,
        selected=True,
    ).exists()
    if (
        event.end_date < timezone.localdate()
        or event.is_finalized
        or group_is_closed
        or event_is_drawn
    ):
        return _application_action_response(
            request,
            event=event,
            applied=True,
            message="모집이 마감되었거나 추첨이 시작되어 취소할 수 없습니다.",
            success=False,
        )

    application.delete()
    return _application_action_response(
        request,
        event=event,
        applied=False,
        message=f"‘{event.title}’ 신청을 취소했습니다.",
    )

@staff_member_required
@require_POST
@transaction.atomic
def delete_event(request, event_id):
    event = get_object_or_404(
        Event.objects.select_for_update(),
        id=event_id,
    )
    event_title = event.title

    event_id = event.pk
    event.delete()
    return _dashboard_event_action_response(
        request,
        event_id=event_id,
        event_title=event_title,
        action="delete",
        message=f"‘{event_title}’ 의전을 삭제했습니다.",
        deleted=True,
    )

@login_required
def event_winners(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    
    # ▼▼▼ 수정: 최종 확정(is_finalized)이 안 된 경우 빈 목록을 보여주거나 메시지 처리 ▼▼▼
    if not event.is_finalized:
        winners = []
        # (선택 사항) 운영진가 아닌 유저가 들어왔을 때 메시지를 띄우고 싶다면 아래 주석 해제
        # if not request.user.is_staff:
        #     messages.info(request, "아직 당첨자 발표 전입니다.")
        #     return redirect('applications:dashboard')
    else:
        winners = Application.objects.filter(event=event, selected=True).select_related('participant')

    return render(request, 'applications/winners.html', {'event': event, 'winners': winners})

# applications/views.py의 event_statistics 함수

@staff_member_required
def event_statistics(request):
    events = Event.objects.order_by('-id').prefetch_related(
        Prefetch('application_set', queryset=Application.objects.select_related('participant')
                 .order_by('-selected', 'participant__username')),
    )
    event_data = []
    for event in events:
        applications = list(event.application_set.all())
        winners = [app for app in applications if app.selected]
        event_data.append({
            'event': event,
            'applications': applications,
            'winners': winners,
            'losers': [app for app in applications if not app.selected],
            'total_applications': len(applications),
            'male_applications': sum(app.participant.gender == 'M' for app in applications),
            'female_applications': sum(app.participant.gender == 'F' for app in applications),
            'total_selected': len(winners),
            'is_drawn': bool(winners),
        })

    return render(request, 'applications/statistics.html', {'event_data': event_data})

def _perform_tiered_lottery(applicants_qs, slots_to_fill):
    """(버그 수정) 우선 선발 및 경쟁 추첨을 수행하는 도우미 함수"""
    
    applicants_list = list(applicants_qs)

    if not applicants_list or slots_to_fill <= 0:
        return []

    priority_applicants = [app for app in applicants_list if getattr(app, "draw_weight", app.participant.weight) >= 3]
    regular_applicants = [app for app in applicants_list if getattr(app, "draw_weight", app.participant.weight) < 3]

    random.shuffle(priority_applicants)
    priority_applicants.sort(key=lambda app: getattr(app, "draw_weight", app.participant.weight), reverse=True)

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
        weights = [max(1, getattr(app, "draw_weight", app.participant.weight)) for app in population]

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
@require_POST
@transaction.atomic
def draw_event(request, event_id):
    """[수정] 1단계: 임시 추첨 (가중치 업데이트 안함)"""
    event = get_object_or_404(
        Event.objects.select_for_update(),
        id=event_id,
    )
    if event.special_lottery_group:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return _dashboard_event_action_response(
                request,
                event_id=event.pk,
                event_title=event.title,
                action="draw",
                message="특별추첨 의전은 묶음 화면에서 한 번에 추첨해 주십시오.",
                success=False,
            )
        messages.info(request, "특별추첨 의전은 묶음 화면에서 추첨해 주십시오.")
        return redirect(
            "applications:special_lottery_review",
            group_id=event.special_lottery_group_id,
        )
    if event.is_finalized: # 최종 확정 필드 체크
        return _dashboard_event_action_response(
            request,
            event_id=event.pk,
            event_title=event.title,
            action="draw",
            message="이미 확정된 의전입니다.",
            success=False,
        )

    all_applicants = Application.objects.filter(event=event).select_related('participant')
    existing_winner_count = all_applicants.filter(selected=True).count()
    if existing_winner_count:
        return _dashboard_event_action_response(
            request,
            event_id=event.pk,
            event_title=event.title,
            action="draw",
            message="이미 임시 추첨이 완료된 의전입니다.",
            drawn=True,
            winner_count=existing_winner_count,
        )

    all_applicants = list(all_applicants)
    draw_weights = calculate_draw_weights(
        [application.participant for application in all_applicants], exclude_event_id=event.pk,
    )
    for application in all_applicants:
        application.draw_weight = draw_weights[application.participant_id]
    winners = []
    if event.male_slots > 0 or event.female_slots > 0:
        # 성비 맞춤 로직 실행
        male_apps = [app for app in all_applicants if app.participant.gender == 'M']
        female_apps = [app for app in all_applicants if app.participant.gender == 'F']
        
        m_winners = _perform_tiered_lottery(male_apps, event.male_slots)
        f_winners = _perform_tiered_lottery(female_apps, event.female_slots)
        
        combined = m_winners + f_winners
        # 총 T/O가 성비 합보다 작을 경우를 대비해 최종 샘플링
        winners = random.sample(combined, min(len(combined), event.total_slots))
        selected_ids = {application.pk for application in winners}
        remaining = [app for app in all_applicants if app.pk not in selected_ids]
        winners.extend(_perform_tiered_lottery(remaining, event.total_slots - len(winners)))
    else:
        # 성비 없는 전체 추첨 실행
        winners = _perform_tiered_lottery(all_applicants, event.total_slots)

    if winners:
        for application in all_applicants:
            application.weight = max(1, application.draw_weight)
        Application.objects.bulk_update(all_applicants, ['weight'])
        event.drawn_at = timezone.now()
        event.save(update_fields=["drawn_at"])
        selected_ids = [w.id for w in winners]
        Application.objects.filter(id__in=selected_ids).update(selected=True)
        return _dashboard_event_action_response(
            request,
            event_id=event.pk,
            event_title=event.title,
            action="draw",
            message=(
                f"임시 추첨으로 {len(winners)}명을 선발했습니다. "
                "명단을 검토해 주십시오."
            ),
            drawn=True,
            winner_count=len(winners),
        )

    return _dashboard_event_action_response(
        request,
        event_id=event.pk,
        event_title=event.title,
        action="draw",
        message="신청자가 없어 추첨할 수 없습니다.",
        success=False,
        drawn=False,
        winner_count=0,
    )

@staff_member_required
@transaction.atomic
def review_winners(request, event_id):
    
    """2단계: 운영진가 명단을 확인하고 수동으로 변경하는 페이지"""
    event = get_object_or_404(
        Event.objects.select_for_update(),
        id=event_id,
    )
    if event.special_lottery_group:
        return redirect(
            "applications:special_lottery_review",
            group_id=event.special_lottery_group_id,
        )
    
    # 당첨자와 탈락자를 나누어 가져옴
    applicants = Application.objects.filter(event=event).select_related('participant', 'event').order_by('participant__name')
    
    if request.method == 'POST':
        if event.is_finalized:
            messages.error(request, '이미 확정된 의전의 명단은 수정할 수 없습니다.')
            return redirect('applications:dashboard')
        # 체크박스 등으로 선택된 ID 목록을 가져와서 업데이트
        try:
            selected_ids = {int(value) for value in request.POST.getlist('selected_applicants')}
        except (TypeError, ValueError):
            messages.error(request, '잘못된 신청 정보가 포함되어 있습니다.')
            return redirect('applications:review_winners', event_id=event.id)
        valid_selected_ids = set(Application.objects.filter(
            event=event,
            id__in=selected_ids,
        ).values_list('id', flat=True))
        if selected_ids != valid_selected_ids:
            messages.error(request, '다른 의전의 신청 정보가 포함되어 있습니다.')
            return redirect('applications:review_winners', event_id=event.id)
        applicants.update(selected=False)
        Application.objects.filter(
            event=event,
            id__in=valid_selected_ids,
        ).update(selected=True)
        if event.drawn_at is None:
            event.drawn_at = timezone.now()
            event.save(update_fields=['drawn_at'])
        messages.success(request, '명단을 임시저장했습니다.')
        return redirect('applications:review_winners', event_id=event.id)

    applicants = list(applicants)
    has_drawn = event.drawn_at is not None or any(app.selected for app in applicants)
    applicants = attach_review_weights(
        applicants, exclude_event_id=event.pk,
        before_draw=(event.drawn_at, event.pk, 0) if has_drawn else None,
    )
    context = {
        'event': event,
        'applicants': applicants,
        'winners_count': sum(app.selected for app in applicants),
        'draw_weights_recorded': bool(applicants) and all(app.weight is not None for app in applicants),
    }
    return render(request, 'applications/review_winners.html', context)

# applications/views.py

# applications/views.py

@staff_member_required
@require_POST
def finalize_event(request, event_id):
    with transaction.atomic():
        event = get_object_or_404(
            Event.objects.select_for_update(),
            id=event_id,
        )

        if event.special_lottery_group:
            messages.info(
                request,
                "특별추첨 의전은 묶음 전체를 한 번에 확정해 주십시오.",
            )
            return redirect(
                "applications:special_lottery_review",
                group_id=event.special_lottery_group_id,
            )

        if event.is_finalized:
            messages.warning(request, "이미 최종 확정된 의전입니다.")
            return redirect('applications:dashboard')

        try:
            selected_ids = {
                int(application_id)
                for application_id in request.POST.getlist(
                    'selected_applicants',
                )
            }
        except (TypeError, ValueError):
            messages.error(request, "잘못된 신청 정보가 포함되어 있습니다.")
            return redirect('applications:review_winners', event_id=event.id)

        valid_selected_ids = set(
            Application.objects.filter(
                event=event,
                id__in=selected_ids,
            ).values_list("id", flat=True),
        )
        if valid_selected_ids != selected_ids:
            messages.error(request, "다른 의전의 신청 정보가 포함되어 있습니다.")
            return redirect('applications:review_winners', event_id=event.id)

        winner_count = len(valid_selected_ids)
        if winner_count == 0:
            messages.error(request, "최소 1명 이상 선택해야 최종 확정할 수 있습니다.")
            return redirect('applications:review_winners', event_id=event.id)

        if winner_count != event.total_slots:
            messages.warning(
                request,
                f"목표 인원({event.total_slots}명)과 다르게 확정됩니다. "
                f"(선택: {winner_count}명)",
            )

        applications = Application.objects.select_for_update().filter(
            event=event,
        )
        participant_ids = list(
            applications.values_list("participant_id", flat=True),
        )
        participants = {
            participant.pk: participant
            for participant in User.objects.select_for_update().filter(id__in=participant_ids).order_by("pk")
        }

        applications.update(selected=False)
        applications.filter(id__in=valid_selected_ids).update(selected=True)

        winner_user_ids = applications.filter(selected=True).values_list(
            'participant_id',
            flat=True,
        )
        User.objects.filter(id__in=winner_user_ids).update(weight=1)

        loser_user_ids = applications.filter(selected=False).values_list(
            'participant_id',
            flat=True,
        )
        User.objects.filter(id__in=loser_user_ids).update(
            weight=F('weight') + 1,
        )

        WeightChange.objects.bulk_create([
            WeightChange(
                user_id=participant_id, source=WeightChange.Source.EVENT, source_id=event.pk,
                before=participants[participant_id].weight,
                after=1 if application_id in valid_selected_ids else participants[participant_id].weight + 1,
                created_by=request.user,
            )
            for application_id, participant_id in applications.values_list('pk', 'participant_id')
        ])

        event.is_finalized = True
        event.save(update_fields=["is_finalized"])

    messages.success(request, f"‘{event.title}’ 명단이 확정되었습니다.")
    return redirect('applications:dashboard')


@login_required
@require_POST
@transaction.atomic
def apply_event(request, event_id):
    event = get_object_or_404(
        Event.objects.select_for_update(),
        id=event_id,
    )
    today = timezone.localdate()

    group_is_closed = (
        event.special_lottery_group
        and (
            event.special_lottery_group.is_drawn
            or event.special_lottery_group.is_finalized
        )
    )
    event_is_drawn = event.drawn_at is not None or Application.objects.filter(
        event=event,
        selected=True,
    ).exists()
    is_closed = (
        event.end_date < today
        or event.is_finalized
        or group_is_closed
        or event_is_drawn
    )
    if is_closed:
        return _application_action_response(
            request,
            event=event,
            applied=False,
            message="모집이 마감되었거나 추첨이 시작되어 신청할 수 없습니다.",
            success=False,
        )

    _, created = Application.objects.get_or_create(
        event=event,
        participant=request.user,
    )
    message = (
        f"‘{event.title}’ 신청이 완료되었습니다."
        if created
        else "이미 신청한 의전입니다."
    )
    return _application_action_response(
        request,
        event=event,
        applied=True,
        message=message,
    )


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
            messages.success(request, f"‘{event.title}’ 의전을 등록했습니다.")
            return redirect('applications:dashboard')
    else:
        form = EventCreateForm()

    return render(request, 'applications/create_event.html', {'form': form})

@login_required
def dashboard(request):
    today = timezone.localdate()
    
    # is_admin 변수와 불필요한 if/else를 제거하여 코드를 단순화합니다.
    # 이벤트 목록은 운영진든 일반 부원든 동일하게 가져옵니다.
    selected_applications = Application.objects.filter(
        event_id=OuterRef("pk"),
        selected=True,
    )
    events = (
        Event.objects.select_related("special_lottery_group")
        .annotate(
            has_selected_application=Exists(selected_applications),
            applicant_count=Count("application"),
        )
        .order_by("-id")
    )

    if request.user.is_staff:
        my_applications = []
        applied_event_ids = set()
    else:
        my_applications = list(
            Application.objects.filter(participant=request.user)
            .select_related("event")
            .order_by("-applied_at"),
        )
        applied_event_ids = {
            application.event_id for application in my_applications
        }

    event_status_list = []
    for event in events:
        # 1. 임시 당첨자가 한 명이라도 있는지 확인
        if event.special_lottery_group:
            is_drawn = event.special_lottery_group.is_drawn
        else:
            is_drawn = event.drawn_at is not None or event.has_selected_application
        # 2. 모델에 추가한 is_finalized 필드 확인
        is_finalized = event.is_finalized 
        
        event_status_list.append({
            'event': event,
            'is_drawn': is_drawn,
            'is_finalized': is_finalized,
            'applicant_count': event.applicant_count,
            'is_open': event.end_date >= today and not is_drawn,
        })

    context = {
        'event_status_list': event_status_list,
        'my_applications': my_applications,
        'applied_event_ids': applied_event_ids,
        'today': today,
        'my_weight': request.user.weight,
    }

    return render(request, 'applications/dashboard.html', context)

# applications/views.py 의 admin_page 함수

# applications/views.py

@staff_member_required
def admin_page(request):
    """운영진 페이지: 검색 및 기수 필터링 기능 추가"""
    search_query = request.GET.get('q', '')
    gen_filter = request.GET.get('gen', '') # 기수 필터 파라미터

    active_users = User.objects.filter(is_active=True).exclude(id=request.user.id)

    # 1. 기수 필터링
    if gen_filter:
        try:
            active_users = active_users.filter(generation=int(gen_filter))
        except ValueError:
            active_users = active_users.none()

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

def _admin_user_response(request, *, ok, message, status=200, **extra):
    """부원 관리 액션 응답: fetch(XHR)면 JSON, 아니면 메시지 + 관리 페이지로 이동."""
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        payload = {"ok": ok, "message": message}
        payload.update(extra)
        return JsonResponse(payload, status=status if not ok else 200)
    (messages.success if ok else messages.error)(request, message)
    return redirect('applications:admin_page')


# 권한 토글 뷰
@staff_member_required
@require_POST
@transaction.atomic
def toggle_accounting_permission(request, user_id):
    target_user = get_object_or_404(User.objects.select_for_update(), id=user_id)
    target_user.can_view_accounting = not target_user.can_view_accounting
    target_user.save(update_fields=["can_view_accounting"])
    status = "부여" if target_user.can_view_accounting else "회수"
    return _admin_user_response(
        request,
        ok=True,
        message=f"{target_user.name or target_user.username}님의 회계 열람 권한을 {status}했습니다.",
        user_id=target_user.pk,
        can_view_accounting=target_user.can_view_accounting,
    )

@staff_member_required
@require_POST
def approve_user(request, user_id):
    """선택한 부원를 활성화(가입 승인)하는 뷰"""
    user_to_approve = get_object_or_404(User, id=user_id)
    user_to_approve.is_active = True
    user_to_approve.save(update_fields=["is_active"])
    return _admin_user_response(
        request, ok=True,
        message=f"{user_to_approve.name or user_to_approve.username}님의 가입을 승인했습니다.",
        user_id=user_to_approve.pk, action="approve",
    )

@staff_member_required
@require_POST
@transaction.atomic
def update_user_weight(request, user_id):
    """운영진가 부원의 누적 가중치를 수정하는 요청을 처리"""
    user_to_update = get_object_or_404(User.objects.select_for_update(), id=user_id)
    try:
        new_weight = int(request.POST.get('weight', ''))
    except (ValueError, TypeError):
        return _admin_user_response(request, ok=False, status=400, message='올바른 가중치를 입력해 주십시오.')
    if new_weight < 1:
        return _admin_user_response(request, ok=False, status=400, message="가중치는 1 이상이어야 합니다.")
    previous_weight = user_to_update.weight
    user_to_update.weight = new_weight
    user_to_update.save(update_fields=["weight"])
    WeightChange.objects.create(
        user=user_to_update, source=WeightChange.Source.MANUAL, source_id=user_to_update.pk,
        before=previous_weight, after=new_weight, created_by=request.user,
    )
    return _admin_user_response(
        request, ok=True,
        message=f"{user_to_update.name or user_to_update.username}님의 가중치를 {new_weight}점으로 수정했습니다.",
        user_id=user_to_update.pk, weight=new_weight,
    )

@staff_member_required
@require_POST
def delete_user(request, user_id):
    """운영진가 부원를 삭제하는 요청을 처리"""
    if request.user.id == user_id:
        return _admin_user_response(request, ok=False, status=409, message="자기 자신의 계정은 삭제할 수 없습니다.")
    user_to_delete = get_object_or_404(User, id=user_id)
    if user_to_delete.is_staff:
        return _admin_user_response(request, ok=False, status=409, message="운영진 계정은 여기서 삭제할 수 없습니다.")
    label = user_to_delete.name or user_to_delete.username
    user_to_delete.delete()
    return _admin_user_response(request, ok=True, message=f"{label}님을 삭제했습니다.", user_id=user_id, action="delete")

@staff_member_required
@require_POST
def reject_user(request, user_id):
    """선택한 부원의 가입을 거절 (삭제)하는 뷰"""
    user_to_reject = get_object_or_404(User, id=user_id, is_active=False)
    label = user_to_reject.name or user_to_reject.username
    user_to_reject.delete()
    return _admin_user_response(request, ok=True, message=f"{label}님의 가입 요청을 거절했습니다.", user_id=user_id, action="reject")


@staff_member_required
@transaction.atomic
def event_update(request, event_id):
    """기존 의전 의전을 수정하는 뷰"""
    event = get_object_or_404(
        Event.objects.select_for_update(),
        id=event_id,
    )

    # ▼▼▼ 이 부분을 추가합니다 ▼▼▼
    # 추첨이 완료되었는지 확인
    is_drawn = event.drawn_at is not None or (
        event.special_lottery_group
        and event.special_lottery_group.is_drawn
    ) or Application.objects.filter(event=event, selected=True).exists()
    if event.is_finalized or is_drawn:
        messages.error(request, "이미 추첨이 완료된 의전은 수정할 수 없습니다.")
        return redirect('applications:dashboard')
    # ▲▲▲ 여기까지 ▲▲▲

    if request.method == 'POST':
        form = EventCreateForm(request.POST, instance=event)
        if form.is_valid():
            form.save()
            messages.success(request, f"‘{event.title}’ 의전이 수정되었습니다.")
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
            user = form.save(commit=False)
            user.save(update_fields=form._meta.fields)
            messages.success(request, f"‘{user_to_update.name}’님의 정보(기수: {user_to_update.generation}기)가 수정되었습니다.")
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
    if not (request.user.is_staff or request.user.can_view_accounting):
        return render(request, 'access_denied.html', status=403)
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
        return render(request, 'access_denied.html', status=403)

    budget_year = get_object_or_404(BudgetYear, year=year)

    generals = Transaction.objects.filter(budget_year=budget_year, event__isnull=True)
    events = AccountingEvent.objects.filter(budget_year=budget_year).select_related("budget_year").annotate(
        summary_income=Sum('transactions__amount', filter=Q(transactions__transaction_type='INCOME')),
        summary_expense=Sum('transactions__amount', filter=Q(transactions__transaction_type='EXPENSE')),
    )

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
    if not (request.user.is_staff or request.user.can_view_accounting):
        return render(request, 'access_denied.html', status=403)
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
        fields = ('date', 'item_name', 'amount', 'category', 'transaction_type', 'description')
        columns = {field: request.POST.getlist(field + '[]') for field in fields}
        count = len(columns['item_name'])
        if not columns['description']:
            columns['description'] = [''] * count
        if count == 0 or any(len(values) != count for values in columns.values()):
            messages.error(request, '회계 내역의 입력 항목 수가 일치하지 않습니다.')
            return redirect('applications:accounting_create')
        transactions_to_create = []
        for i in range(count):
            data = {field: columns[field][i] for field in fields}
            data.update(budget_year=request.POST.get('budget_year'), event=request.POST.get('accounting_event', ''))
            form = AccountingTransactionForm(data)
            if not form.is_valid():
                messages.error(request, f'{i + 1}행의 날짜, 금액, 항목, 구분 및 행사·연도를 확인해 주십시오.')
                return redirect('applications:accounting_create')
            transactions_to_create.append(form.save(commit=False))
        with transaction.atomic():
            Transaction.objects.bulk_create(transactions_to_create)
        budget_year = transactions_to_create[0].budget_year
        messages.success(request, f'{len(transactions_to_create)}건의 내역이 추가되었습니다.')
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

    transactions = Transaction.objects.filter(budget_year=budget_year).select_related('event').order_by('date')
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
        form = AccountingEventForm(request.POST)
        if not form.is_valid():
            messages.error(request, '행사명, 날짜 및 회계 연도를 확인해 주십시오.')
            return redirect('applications:event_create')
        event = form.save()
        return redirect('applications:accounting_year_list', year=event.budget_year.year)

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
        data = request.POST.copy()
        data['event'] = request.POST.get('accounting_event', '')
        form = AccountingTransactionForm(data, instance=transaction)
        if not form.is_valid():
            messages.error(request, '날짜, 금액, 항목, 구분 및 행사·연도를 확인해 주십시오.')
            return redirect('applications:accounting_update', pk=transaction.pk)
        transaction = form.save()
        messages.success(request, f"‘{transaction.item_name}’ 내역이 수정되었습니다.")
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
@require_POST
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

# [운영진 전용] 행사 정보 수정
@staff_member_required
def accounting_event_update(request, pk):
    event = get_object_or_404(AccountingEvent, pk=pk)
    
    if request.method == 'POST':
        data = request.POST.copy()
        data['budget_year'] = event.budget_year_id
        form = AccountingEventForm(data, instance=event)
        if not form.is_valid():
            messages.error(request, '행사명과 날짜를 확인해 주십시오.')
            return redirect('applications:accounting_event_update', pk=event.pk)
        event = form.save()
        messages.success(request, f"행사 ‘{event.name}’ 정보가 수정되었습니다.")
        return redirect('applications:accounting_year_list', year=event.budget_year.year)

    context = {
        'event': event,
        'years': BudgetYear.objects.all().order_by('-year'),
    }
    return render(request, 'applications/accounting_event_update_form.html', context)

# [운영진 전용] 행사 삭제 (삭제 시 그 안의 내역들도 같이 지워짐)
@staff_member_required
@require_POST
def accounting_event_delete(request, pk):
    if request.method == 'POST':
        event = get_object_or_404(AccountingEvent, pk=pk)
        target_year = event.budget_year.year
        event.delete() # CASCADE 설정에 의해 내부 Transaction도 자동 삭제됨
        messages.success(request, "행사가 삭제되었습니다.")
        return redirect('applications:accounting_year_list', year=target_year)
    return redirect('applications:accounting_list')

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



def _schedule_payload(schedule):
    return {
        "id": schedule.pk,
        "title": schedule.title,
        "start": schedule.start_at.astimezone(KST).isoformat(),
        "end": schedule.end_at.astimezone(KST).isoformat() if schedule.end_at else None,
        "color": schedule.color or "#1E3A8A",
        "content": schedule.content or "",
        "allDay": False,
        "extendedProps": {"content": schedule.content or ""},
    }


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

        schedule = ClubSchedule.objects.create(
            title=(data.get("title", "").strip() or "제목 없음"),
            start_at=start_at,
            end_at=end_at,
            content=data.get("content", "") or "",
            color=data.get("color", "#1E3A8A") or "#1E3A8A",
        )
        return JsonResponse({"status": "success", **_schedule_payload(schedule)})

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

        return JsonResponse({"status": "success", **_schedule_payload(schedule)})

    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=400)

@staff_member_required
@require_POST
def delete_schedule(request, pk):
    schedule = get_object_or_404(ClubSchedule, pk=pk)
    schedule.delete()
    return JsonResponse({"status": "success"})

# -----------------------------------------------------------
# [운영진 전용] 1. 새 회계 연도(기수) 생성 및 활성화
# -----------------------------------------------------------
@staff_member_required
@require_POST
def create_budget_year(request):
    next_url = request.POST.get('next', '')
    if not url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        next_url = reverse('applications:accounting_main')

    if request.method == 'POST':
        reason = request.POST.get('reason', '').strip()
        if not reason:
            messages.error(request, '생성 사유를 입력해 주십시오.')
            return HttpResponseRedirect(next_url)
        try:
            year_val = int(request.POST.get('year', ''))
        except (ValueError, TypeError):
            year_val = None
        if year_val is None or not 1 <= year_val <= 9999:
            messages.error(request, "연도를 입력해 주십시오.")
            return HttpResponseRedirect(next_url)

        with transaction.atomic():
            # 기존 활성 연도를 모두 비활성화한 뒤 새 연도를 활성화
            BudgetYear.objects.filter(is_active=True).update(is_active=False)
            budget_year, created = BudgetYear.objects.update_or_create(
                year=year_val,
                defaults={'is_active': True},
                create_defaults={'is_active': True, 'reason': reason, 'created_by': request.user},
            )

        status_msg = "생성" if created else "활성화"
        messages.success(request, f"{year_val}년 회계 연도를 {status_msg}했습니다.")
        return HttpResponseRedirect(next_url)

    return HttpResponseRedirect(next_url)

# -----------------------------------------------------------
# [운영진 전용] 2. 현재 활성 기수 데이터 전체 초기화
# -----------------------------------------------------------
@staff_member_required
@require_POST
@transaction.atomic
def initialize_accounting_data(request):
    """현재 활성화된 기수의 모든 내역과 행사를 삭제"""
    if request.method == 'POST':
        active_year = BudgetYear.objects.select_for_update().filter(is_active=True).first()
        
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
