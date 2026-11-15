from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from .models import Application, Event, SpecialLotteryGroup

pytestmark = pytest.mark.django_db


@pytest.fixture
def flow(client):
    User = get_user_model()
    staff = User.objects.create_user(username='snapshot-staff', is_staff=True)
    first = User.objects.create_user(username='snapshot-first', weight=1)
    second = User.objects.create_user(username='snapshot-second', weight=2)
    client.force_login(staff)
    return first, second


def event(users, **kwargs):
    obj = Event.objects.create(title='Snapshot', start_date=timezone.localdate(), end_date=timezone.localdate(),
                                total_slots=1, male_slots=0, female_slots=0, **kwargs)
    for user in users:
        Application.objects.create(event=obj, participant=user)
    return obj


def test_general_review_keeps_original_draw_weights_after_later_draws_and_edits(client, flow):
    first, second = flow
    target = event(flow)
    with patch('s_angel.applications.views.random.choices', side_effect=lambda population, **kwargs: [population[0]]):
        client.post(reverse('applications:draw_event', args=[target.pk]))
    original = dict(target.application_set.values_list('participant_id', 'weight'))
    assert original == {first.pk: 1, second.pk: 2}
    later = event(flow, drawn_at=timezone.now() + timedelta(seconds=1))
    later.application_set.filter(participant=second).update(selected=True)
    get_user_model().objects.filter(pk=first.pk).update(weight=10)
    client.post(reverse('applications:review_winners', args=[target.pk]),
                {'selected_applicants': [target.application_set.get(participant=second).pk]})
    response = client.get(reverse('applications:review_winners', args=[target.pk]))
    rows = {app.participant_id: app for app in response.context['applicants']}
    assert {pk: app.draw_weight for pk, app in rows.items()} == original
    assert rows[first.pk].confirmed_weight == 10
    assert response.context['draw_weights_recorded']


@pytest.mark.parametrize('mode,expected', [('BALANCED', (1, 0.5)), ('WEIGHTED', (1, 1)), ('EQUAL', (1, 1))])
def test_special_review_keeps_actual_mode_adjusted_weights(client, flow, mode, expected):
    first, second = flow
    group = SpecialLotteryGroup.objects.create(name='Snapshot group', draw_mode=mode)
    events = [event(flow, special_lottery_group=group, special_lottery_order=i) for i in range(2)]
    with patch('s_angel.applications.special_lottery.random.choices', side_effect=lambda population, **kwargs: [population[0]]):
        client.post(reverse('applications:special_lottery_draw', args=[group.pk]))
    assert tuple(obj.application_set.get(participant=first).weight for obj in events) == expected
    later = event(flow, drawn_at=timezone.now() + timedelta(seconds=1))
    later.application_set.filter(participant=second).update(selected=True)
    response = client.get(reverse('applications:special_lottery_review', args=[group.pk]))
    assert response.context['draw_weights_recorded']
    rows = response.context['event_rows']
    assert tuple(next(app.draw_weight for app in row['applications'] if app.participant_id == first.pk) for row in rows) == expected
    # Changing temporary winners must never replace the weight used in the draw.
    data = {f'event_{obj.pk}_selected': [obj.application_set.get(participant=second).pk] for obj in events}
    client.post(reverse('applications:special_lottery_save_roster', args=[group.pk]), data)
    assert tuple(obj.application_set.get(participant=first).weight for obj in events) == expected


def test_legacy_review_excludes_later_draws(client, flow):
    first, second = flow
    now = timezone.now()
    earlier = event(flow, drawn_at=now - timedelta(minutes=2))
    earlier.application_set.filter(participant=first).update(selected=True)
    target = event(flow, drawn_at=now - timedelta(minutes=1))
    later = event(flow, drawn_at=now)
    later.application_set.filter(participant=second).update(selected=True)
    response = client.get(reverse('applications:review_winners', args=[target.pk]))
    assert {app.participant_id: app.draw_weight for app in response.context['applicants']} == {first.pk: 1, second.pk: 3}
    assert not response.context['draw_weights_recorded']


@pytest.mark.parametrize('special', [False, True])
def test_finalized_review_hides_weight_metadata_and_explanation(client, flow, special):
    if special:
        group = SpecialLotteryGroup.objects.create(name='Finalized', is_drawn=True, is_finalized=True)
        event(flow, special_lottery_group=group, is_finalized=True)
        url = reverse('applications:special_lottery_review', args=[group.pk])
    else:
        obj = event(flow, is_finalized=True)
        url = reverse('applications:review_winners', args=[obj.pk])
    response = client.get(url)
    html = response.content.decode()
    assert response.status_code == 200
    assert '추첨 가중치' not in html
    assert '확정 가중치' not in html
    assert '미확정 의전' not in html
