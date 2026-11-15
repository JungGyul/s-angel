from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from .models import Application, Event, SpecialLotteryGroup, WeightChange
from .weight_service import calculate_draw_weights

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff(client):
    user = get_user_model().objects.create_user(username='weight-manager', is_staff=True)
    client.force_login(user)
    return user


def member(name, weight=5):
    return get_user_model().objects.create_user(username=name, weight=weight)


def event(title, users, selected=None, drawn_at=None):
    obj = Event.objects.create(title=title, start_date=timezone.localdate(), end_date=timezone.localdate(),
                                total_slots=1, male_slots=0, female_slots=0, drawn_at=drawn_at)
    for user in users:
        Application.objects.create(event=obj, participant=user, selected=user == selected)
    return obj


def finalize(client, obj, winner):
    app = obj.application_set.get(participant=winner)
    return client.post(reverse('applications:finalize_event', args=[obj.pk]), {'selected_applicants': [app.pk]})


def test_consecutive_draw_uses_virtual_weights_for_priority_without_writing_confirmed_weights(client, staff):
    first, second = member('high', 5), member('rising', 2)
    earlier = event('First', [first, second], selected=first, drawn_at=timezone.now())
    later = event('Second', [first, second])
    client.post(reverse('applications:draw_event', args=[later.pk]))
    assert later.application_set.get(participant=second).selected
    later.refresh_from_db()
    assert later.drawn_at is not None
    first.refresh_from_db()
    second.refresh_from_db()
    assert (first.weight, second.weight) == (5, 2)
    assert not WeightChange.objects.exists()
    response = client.get(reverse('applications:review_winners', args=[later.pk]))
    rows = {app.participant_id: app for app in response.context['applicants']}
    assert (rows[first.pk].draw_weight, rows[first.pk].confirmed_weight) == (1, 5)
    assert (rows[second.pk].draw_weight, rows[second.pk].confirmed_weight) == (3, 2)
    assert response.status_code == 200


def test_proportional_selection_uses_virtual_weights(client, staff):
    first, second = member('proportional-first', 2), member('proportional-second', 1)
    event('Earlier', [first, second], selected=first, drawn_at=timezone.now())
    later = event('Later', [first, second])
    captured = {}
    def choose(population, weights, k):
        captured.update({app.participant_id: weight for app, weight in zip(population, weights)})
        return [population[0]]
    with patch('s_angel.applications.views.random.choices', side_effect=choose):
        client.post(reverse('applications:draw_event', args=[later.pk]))
    assert captured == {first.pk: 1, second.pk: 2}


@pytest.mark.parametrize('reverse_order,expected', [(False, (2, 1)), (True, (1, 2))])
def test_confirmation_order_is_preserved_without_double_application(client, staff, reverse_order, expected):
    first, second = member('order-first'), member('order-second')
    earlier = event('Earlier', [first, second], selected=first, drawn_at=timezone.now())
    later = event('Later', [first, second], selected=second, drawn_at=timezone.now() + timedelta(seconds=1))
    pair = [(earlier, first), (later, second)]
    if reverse_order:
        pair.reverse()
    finalize(client, *pair[0])
    preview = calculate_draw_weights([first, second])
    assert (preview[first.pk], preview[second.pk]) == expected
    finalize(client, *pair[1])
    first.refresh_from_db()
    second.refresh_from_db()
    assert (first.weight, second.weight) == expected
    assert calculate_draw_weights([first, second]) == {first.pk: first.weight, second.pk: second.weight}
    assert WeightChange.objects.count() == 4
    assert set(WeightChange.objects.values_list('created_by_id', flat=True)) == {staff.pk}
    finalize(client, *pair[1])
    assert WeightChange.objects.count() == 4


def test_final_roster_is_used_and_later_roster_is_never_redrawn(client, staff):
    first, second = member('edited-first'), member('edited-second')
    earlier = event('Edited', [first, second], selected=first, drawn_at=timezone.now())
    later = event('Unaffected', [first, second], selected=first, drawn_at=timezone.now() + timedelta(seconds=1))
    later_ids = set(later.application_set.filter(selected=True).values_list('pk', flat=True))
    client.post(reverse('applications:review_winners', args=[earlier.pk]),
                {'selected_applicants': [earlier.application_set.get(participant=second).pk]})
    finalize(client, earlier, second)
    first.refresh_from_db()
    second.refresh_from_db()
    assert (first.weight, second.weight) == (6, 1)
    assert set(later.application_set.filter(selected=True).values_list('pk', flat=True)) == later_ids
    assert WeightChange.objects.get(user=first, source_id=earlier.pk).after == 6


def test_draw_order_uses_timestamp_then_legacy_ids_and_ignores_undrawn_events():
    user, other = member('timeline-user'), member('timeline-other')
    later_id_earlier_time = event('Low ID late time', [user, other], selected=user,
                                 drawn_at=timezone.now() + timedelta(hours=1))
    earlier_time = event('High ID early time', [user, other], selected=other, drawn_at=timezone.now())
    assert calculate_draw_weights([user])[user.pk] == 1
    Event.objects.filter(pk__in=[later_id_earlier_time.pk, earlier_time.pk]).update(drawn_at=None)
    assert calculate_draw_weights([user])[user.pk] == 2
    event('Undrawn', [user])
    assert calculate_draw_weights([user])[user.pk] == 2


def test_virtual_special_adjustment_includes_non_candidate_denominators():
    user, other = member('special-user', 4), member('special-other', 4)
    group = SpecialLotteryGroup.objects.create(name='Pending group', is_drawn=True, drawn_at=timezone.now())
    for index in range(2):
        obj = event(f'Group {index}', [user, other], selected=other)
        obj.special_lottery_group = group
        obj.save(update_fields=['special_lottery_group'])
    # Both candidates apply twice. Other wins all => candidate below group rate.
    assert calculate_draw_weights([user])[user.pk] == 5
    assert calculate_draw_weights([other])[other.pk] == 1
    assert calculate_draw_weights([user], exclude_group_id=group.pk)[user.pk] == 4


def test_manual_edit_is_audited_and_event_deletion_retains_weights_and_audit(client, staff):
    first, second = member('manual-first'), member('manual-second')
    client.post(reverse('applications:update_user_weight', args=[first.pk]), {'weight': 7})
    change = WeightChange.objects.get(source=WeightChange.Source.MANUAL)
    assert (change.source_id, change.before, change.after, change.created_by_id) == (first.pk, 5, 7, staff.pk)
    obj = event('Delete confirmed', [first, second], selected=second, drawn_at=timezone.now())
    finalize(client, obj, second)
    client.post(reverse('applications:delete_event', args=[obj.pk]))
    first.refresh_from_db()
    assert first.weight == 8
    assert WeightChange.objects.filter(source=WeightChange.Source.EVENT, source_id=obj.pk).count() == 2
    assert calculate_draw_weights([first])[first.pk] == 8


def test_create_and_roster_save_messages(client, staff):
    from django.contrib.messages import get_messages
    response = client.post(reverse('applications:create_event'), {'title': '등록 테스트',
                           'start_date': timezone.localdate(), 'end_date': timezone.localdate(), 'total_slots': 1})
    assert [str(message) for message in get_messages(response.wsgi_request)] == ['‘등록 테스트’ 의전을 등록했습니다.']
    obj = Event.objects.get(title='등록 테스트')
    user = member('roster-saver')
    application = Application.objects.create(event=obj, participant=user)
    response = client.post(reverse('applications:review_winners', args=[obj.pk]), {'selected_applicants': [application.pk]})
    assert '명단을 임시저장했습니다.' in [str(message) for message in get_messages(response.wsgi_request)]
