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

@staff_member_required
def event_statistics(request):
    events = Event.objects.all()

    event_data = []
    for event in events:
        total_applications = Application.objects.filter(event=event).count()
        male_applications = Application.objects.filter(event=event, participant__gender='M').count()
        female_applications = Application.objects.filter(event=event, participant__gender='F').count()
        total_selected = Application.objects.filter(event=event, selected=True).count()
        winners = Application.objects.filter(event=event, selected=True)

        event_data.append({
            'event': event,
            'total_applications': total_applications,
            'male_applications': male_applications,
            'female_applications': female_applications,
            'total_selected': total_selected,
            'winners': winners,  # 추가
        })

    return render(request, 'applications/statistics.html', {'event_data': event_data})

@staff_member_required
def draw_event(request, event_id):
    event = get_object_or_404(Event, id=event_id)

    if not Application.objects.filter(event=event, selected=True).exists():
        male_applicants = Application.objects.filter(event=event, participant__gender='M')
        female_applicants = Application.objects.filter(event=event, participant__gender='F')
        all_applicants = Application.objects.filter(event=event)

        # 🎯 지원자가 아예 없으면 그냥 리다이렉트
        if all_applicants.count() == 0:
            return redirect('applications:dashboard')

        if (event.male_slots == 0 and event.female_slots == 0):
            # ⭐ 성비 설정 없이 전체 중 total_slots 만큼 뽑기
            all_weights = list(all_applicants.values_list('weight', flat=True))
            winners = random.choices(
                population=list(all_applicants),
                weights=all_weights,
                k=min(event.total_slots, all_applicants.count())
            )
        else:
            # ⭐ 성비 설정이 있으면 남녀 따로 뽑기
            male_weights = list(male_applicants.values_list('weight', flat=True))
            female_weights = list(female_applicants.values_list('weight', flat=True))

            male_winners = []
            female_winners = []

            if male_applicants.exists():
                male_winners = random.choices(
                    population=list(male_applicants),
                    weights=male_weights,
                    k=min(event.male_slots, male_applicants.count())
                )

            if female_applicants.exists():
                female_winners = random.choices(
                    population=list(female_applicants),
                    weights=female_weights,
                    k=min(event.female_slots, female_applicants.count())
                )

            winners = male_winners + female_winners

        # selected 업데이트
        selected_ids = [winner.id for winner in winners]
        for app in Application.objects.filter(id__in=selected_ids):
            app.selected = True
            app.weight = 1 
            app.save()

        # ❗ 떨어진 사람은 weight +1
        for app in Application.objects.filter(event=event, selected=False):
            app.weight += 1
            app.save()

    return redirect('applications:dashboard')



@login_required
def apply_event(request, event_id):
    event = get_object_or_404(Event, id=event_id)

    today = datetime.date.today()

    # 1. 마감된 이벤트는 신청 금지
    if event.end_date < today:
        return redirect('applications:dashboard')

    # 2. 이미 신청한 경우도 막기
    if Application.objects.filter(event=event, participant=request.user).exists():
        return redirect('applications:dashboard')

    # 3. 정상적인 경우만 신청 생성
    previous_failures = Application.objects.filter(
        participant=request.user,
        selected=False
    ).count()

    Application.objects.create(
        event=event,
        participant=request.user,
        weight=1 + previous_failures
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

    if request.user.is_staff:
        events = Event.objects.all()
        is_admin = True
    else:
        events = Event.objects.all()
        is_admin = False

    my_applications = Application.objects.filter(participant=request.user)
    applied_event_ids = my_applications.values_list('event_id', flat=True)

    # 🎯 추첨 완료 체크
    event_status_list = []
    for event in events:
        is_closed = event.end_date < today
        is_drawn = Application.objects.filter(event=event, selected=True).exists()

        event_status_list.append({
            'event': event,
            'is_closed': is_closed,
            'is_drawn': is_drawn,
        })

    context = {
        'event_status_list': event_status_list,  # 🎯 events 대신 event_status_list 넘김
        'is_admin': is_admin,
        'my_applications': my_applications,
        'applied_event_ids': applied_event_ids,
        'today': today,
    }

    return render(request, 'applications/dashboard.html', context)
