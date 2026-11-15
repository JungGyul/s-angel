import json

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from .forms import UserInfoUpdateForm
from .models import AccountingEvent, Application, BudgetYear, Event, SpecialLotteryGroup, Transaction

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff(client):
    user = get_user_model().objects.create_user(username='review-manager', is_staff=True)
    client.force_login(user)
    return user


@pytest.mark.parametrize('total,male,female,genders', [
    (5, 1, 1, ['M', 'M', 'F', None, None]),
    (3, 2, 1, ['F', 'F', None]),
])
def test_general_draw_fills_remaining_slots(client, staff, total, male, female, genders):
    event = Event.objects.create(title='Fill seats', start_date=timezone.localdate(),
                                 end_date=timezone.localdate(), total_slots=total,
                                 male_slots=male, female_slots=female)
    for index, gender in enumerate(genders):
        participant = get_user_model().objects.create_user(username=f'draw-person-{index}', gender=gender)
        Application.objects.create(event=event, participant=participant)
    client.post(reverse('applications:draw_event', args=[event.pk]))
    assert event.application_set.filter(selected=True).count() == total


def test_one_event_special_group_cannot_be_finalized(client, staff):
    group = SpecialLotteryGroup.objects.create(name='One left', is_drawn=True)
    event = Event.objects.create(title='Remaining', start_date=timezone.localdate(), end_date=timezone.localdate(),
                                 total_slots=1, male_slots=0, female_slots=0, special_lottery_group=group)
    participant = get_user_model().objects.create_user(username='single-event-user', weight=5)
    app = Application.objects.create(event=event, participant=participant, selected=True)
    response = client.post(reverse('applications:special_lottery_finalize', args=[group.pk]),
                           {f'selected_{event.pk}': [app.pk]})
    assert response.status_code == 302
    group.refresh_from_db()
    participant.refresh_from_db()
    assert not group.is_finalized and participant.weight == 5
    assert not group.settlements.exists()


def test_update_user_info_preserves_concurrently_changed_weight(client, staff, monkeypatch):
    user = get_user_model().objects.create_user(username='changed-member', weight=2)
    original = UserInfoUpdateForm.is_valid
    def valid(form):
        result = original(form)
        get_user_model().objects.filter(pk=user.pk).update(weight=9)
        return result
    monkeypatch.setattr(UserInfoUpdateForm, 'is_valid', valid)
    response = client.post(reverse('applications:update_user_info', args=[user.pk]), {'gender': 'F', 'generation': 22})
    assert response.status_code == 302
    user.refresh_from_db()
    assert user.weight == 9 and user.generation == 22


@pytest.fixture
def year():
    return BudgetYear.objects.create(year=2026)


def transaction_data(year):
    return {'budget_year': year.pk, 'date[]': ['2026-11-15'], 'item_name[]': ['Receipt'],
            'amount[]': ['100'], 'category[]': ['Other'], 'transaction_type[]': ['INCOME'], 'description[]': ['']}


@pytest.mark.parametrize('change', [
    {'date[]': ['invalid']}, {'amount[]': ['-1']}, {'amount[]': ['text']},
    {'amount[]': ['2147483648']}, {'amount[]': []}, {'date[]': ['2026-11-15', '2026-11-16']},
    {'transaction_type[]': ['UNKNOWN']}, {'budget_year': 'invalid'}, {'accounting_event': 'invalid'},
])
def test_accounting_batch_rejects_invalid_input_without_500(client, staff, year, change):
    data = transaction_data(year)
    data.update(change)
    response = client.post(reverse('applications:accounting_create'), data)
    assert response.status_code == 302
    assert not Transaction.objects.exists()


def test_accounting_batch_checks_event_year_and_keeps_batch_atomic(client, staff, year):
    other_year = BudgetYear.objects.create(year=2027)
    event = AccountingEvent.objects.create(budget_year=other_year, name='Other year', date=timezone.localdate())
    data = transaction_data(year)
    data['accounting_event'] = event.pk
    assert client.post(reverse('applications:accounting_create'), data).status_code == 302
    assert not Transaction.objects.exists()
    data = transaction_data(year)
    assert client.post(reverse('applications:accounting_create'), data).status_code == 302
    saved = Transaction.objects.get()
    assert saved.amount == 100
    invalid = {'budget_year': year.pk, 'date': 'invalid', 'item_name': 'Changed', 'amount': 100,
               'category': 'Other', 'transaction_type': 'INCOME'}
    assert client.post(reverse('applications:accounting_update', args=[saved.pk]), invalid).status_code == 302
    saved.refresh_from_db()
    assert saved.item_name == 'Receipt'


def test_accounting_event_invalid_date_is_reported(client, staff, year):
    response = client.post(reverse('applications:event_create'), {'budget_year': year.pk, 'name': 'Event', 'date': 'bad'})
    assert response.status_code == 302
    assert not AccountingEvent.objects.exists()


def test_accounting_readers_do_not_see_staff_export_links(client, year):
    member = get_user_model().objects.create_user(username='ledger-reader', can_view_accounting=True)
    event = AccountingEvent.objects.create(budget_year=year, name='Event', date=timezone.localdate())
    client.force_login(member)
    export = reverse('applications:export_accounting_excel', args=[year.year])
    for url in [reverse('applications:accounting_year_list', args=[year.year]),
                reverse('applications:accounting_event_detail', args=[event.pk])]:
        response = client.get(url)
        assert response.status_code == 200
        assert export not in response.content.decode()
