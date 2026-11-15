"""Special draws consume provisional weights and settle only confirmed values."""
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from .models import Application, Event, SpecialLotteryGroup, WeightChange
from .special_lottery import _build_review_context

pytestmark = pytest.mark.django_db


@pytest.fixture
def flow(client):
    User = get_user_model()
    staff = User.objects.create_user(username='special-weight-manager', is_staff=True)
    first = User.objects.create_user(username='special-weight-first', weight=4)
    second = User.objects.create_user(username='special-weight-second', weight=2)
    client.force_login(staff)
    group = SpecialLotteryGroup.objects.create(name='Virtual weights', draw_mode=SpecialLotteryGroup.DrawMode.WEIGHTED)
    events = [Event.objects.create(
        title=f'Special day {index}', start_date=timezone.localdate(), end_date=timezone.localdate(),
        total_slots=1, male_slots=0, female_slots=0, special_lottery_group=group,
        special_lottery_order=index,
    ) for index in range(2)]
    applications = {}
    for event in events:
        applications[event.pk] = [Application.objects.create(event=event, participant=user) for user in (first, second)]
    previous = Event.objects.create(
        title='Earlier general draw', start_date=timezone.localdate(), end_date=timezone.localdate(),
        total_slots=1, male_slots=0, female_slots=0, drawn_at=timezone.now() - timedelta(minutes=1),
    )
    Application.objects.create(event=previous, participant=first, selected=True)
    Application.objects.create(event=previous, participant=second, selected=False)
    return staff, first, second, group, events, applications


@pytest.mark.parametrize('mode,expected_second', [
    (SpecialLotteryGroup.DrawMode.WEIGHTED, [1, 3]),
    (SpecialLotteryGroup.DrawMode.BALANCED, [0.5, 3]),
    (SpecialLotteryGroup.DrawMode.EQUAL, [1, 1]),
])
def test_special_draw_uses_prior_general_result_and_keeps_mode_rules(client, flow, mode, expected_second):
    _, first, second, group, _, _ = flow
    group.draw_mode = mode
    group.save(update_fields=['draw_mode'])
    captured = []
    def choose(population, *, weights, k):
        captured.append(list(weights))
        return [population[0]]
    with patch('s_angel.applications.special_lottery.random.choices', side_effect=choose):
        response = client.post(reverse('applications:special_lottery_draw', args=[group.pk]))
    assert response.status_code == 302
    assert captured[0] == ([1, 1] if mode == SpecialLotteryGroup.DrawMode.EQUAL else [1, 3])
    assert captured[1] == expected_second
    group.refresh_from_db()
    first.refresh_from_db()
    second.refresh_from_db()
    assert group.drawn_at is not None
    assert (first.weight, second.weight) == (4, 2)
    assert not WeightChange.objects.exists()


def test_special_finalization_audits_final_roster_without_provisional_double_apply(client, flow):
    staff, first, second, group, events, applications = flow
    group.is_drawn = True
    group.drawn_at = timezone.now()
    group.save(update_fields=['is_drawn', 'drawn_at'])
    Application.objects.filter(participant=first, event__in=events).update(selected=True)
    data = {f'event_{event.pk}_selected': [applications[event.pk][1].pk] for event in events}
    url = reverse('applications:special_lottery_finalize', args=[group.pk])
    response = client.post(url, data)
    assert response.status_code == 302
    first.refresh_from_db()
    second.refresh_from_db()
    assert (first.weight, second.weight) == (5, 1)
    changes = WeightChange.objects.filter(source=WeightChange.Source.SPECIAL, source_id=group.pk)
    assert set(changes.values_list('user_id', 'before', 'after', 'created_by_id')) == {
        (first.pk, 4, 5, staff.pk), (second.pk, 2, 1, staff.pk),
    }
    client.post(url, data)
    assert changes.count() == 2
    first.refresh_from_db()
    assert first.weight == 5


def test_special_review_excludes_own_current_roster(client, flow):
    _, first, second, group, events, applications = flow
    group.is_drawn = True
    group.drawn_at = timezone.now()
    group.save(update_fields=['is_drawn', 'drawn_at'])
    Application.objects.filter(event__in=events, participant=first).update(selected=True)
    context = _build_review_context(group)
    stats = {row['participant'].pk: row for row in context['user_stats']}
    assert (stats[first.pk]['draw_weight'], stats[first.pk]['confirmed_weight']) == (1, 4)
    assert (stats[second.pk]['draw_weight'], stats[second.pk]['confirmed_weight']) == (3, 2)
    for row in context['event_rows']:
        apps = {app.participant_id: app for app in row['applications']}
        assert (apps[first.pk].draw_weight, apps[first.pk].confirmed_weight) == (1, 4)
        assert (apps[second.pk].draw_weight, apps[second.pk].confirmed_weight) == (3, 2)


def test_roster_first_save_records_and_preserves_draw_timestamp(client, flow):
    _, _, _, group, events, applications = flow
    data = {f'event_{event.pk}_selected': [applications[event.pk][0].pk] for event in events}
    url = reverse('applications:special_lottery_save_roster', args=[group.pk])
    client.post(url, data)
    group.refresh_from_db()
    original = group.drawn_at
    assert original is not None
    client.post(url, data)
    group.refresh_from_db()
    assert group.drawn_at == original


def test_special_equal_rate_settlement_keeps_weights_and_is_audited(client, flow):
    _, first, second, group, events, applications = flow
    group.is_drawn = True
    group.drawn_at = timezone.now()
    group.save(update_fields=['is_drawn', 'drawn_at'])
    data = {
        f'event_{events[0].pk}_selected': [applications[events[0].pk][0].pk],
        f'event_{events[1].pk}_selected': [applications[events[1].pk][1].pk],
    }
    client.post(reverse('applications:special_lottery_finalize', args=[group.pk]), data)
    assert set(WeightChange.objects.filter(source=WeightChange.Source.SPECIAL, source_id=group.pk)
               .values_list('user_id', 'before', 'after')) == {(first.pk, 4, 4), (second.pk, 2, 2)}
