from pprint import saferepr

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from .models import AccountingEvent, Application, BudgetYear, Event, SpecialLotteryGroup, Transaction

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff(client):
    user = get_user_model().objects.create_user(username='query-manager', is_staff=True)
    client.force_login(user)
    return user


def add_applicants(event, start, end, *, related_events=()):
    for index in range(start, end):
        user = get_user_model().objects.create_user(username=f'query-{event.pk}-{index}', name=f'Name {index}')
        Application.objects.create(event=event, participant=user, selected=index < 3)
        for related_event in related_events:
            Application.objects.create(event=related_event, participant=user, selected=index < 3)


def new_event():
    return Event.objects.create(title='Scaling', start_date=timezone.localdate(), end_date=timezone.localdate(),
                                 total_slots=3, male_slots=0, female_slots=0)


def capture(client, url):
    with CaptureQueriesContext(connection) as queries:
        response = client.get(url)
    assert response.status_code == 200
    return response, list(queries)


def test_general_review_query_count_is_constant(client, staff, django_assert_num_queries):
    event = new_event()
    add_applicants(event, 0, 5)
    url = reverse('applications:review_winners', args=[event.pk])
    capture(client, url)
    _, small = capture(client, url)
    add_applicants(event, 5, 30)
    with django_assert_num_queries(len(small)):
        response, large = capture(client, url)
    # Debug Toolbar's template panel calls saferepr on context values.
    with django_assert_num_queries(0):
        saferepr(response.context['applicants'])
    assert len(large) == len(small)


def test_special_review_query_count_is_constant(client, staff, django_assert_num_queries):
    group = SpecialLotteryGroup.objects.create(name='Scaling group', is_drawn=True)
    event = new_event()
    event.special_lottery_group = group
    event.save(update_fields=['special_lottery_group'])
    other = new_event()
    other.special_lottery_group = group
    other.save(update_fields=['special_lottery_group'])
    add_applicants(event, 0, 5, related_events=[other])
    url = reverse('applications:special_lottery_review', args=[group.pk])
    capture(client, url)
    _, small = capture(client, url)
    add_applicants(event, 5, 30, related_events=[other])
    with django_assert_num_queries(len(small)):
        response, large = capture(client, url)
    with django_assert_num_queries(0):
        saferepr(response.context['event_rows'])
    assert len(large) == len(small)


def test_accounting_event_query_count_is_constant(client, staff, django_assert_num_queries):
    year = BudgetYear.objects.create(year=2030, is_active=True)
    def add_event(index):
        event = AccountingEvent.objects.create(budget_year=year, name=f'Ledger {index}', date=timezone.localdate())
        Transaction.objects.create(event=event, budget_year=year, date=timezone.localdate(), item_name='Income',
                                   amount=100, category='Other', transaction_type='INCOME')
    add_event(0)
    url = reverse('applications:accounting_year_list', args=[year.year])
    capture(client, url)
    _, small = capture(client, url)
    for index in range(1, 6):
        add_event(index)
    with django_assert_num_queries(len(small)):
        response, large = capture(client, url)
    with django_assert_num_queries(0):
        saferepr(response.context['timeline'])
    assert response.context['total_income'] == 600
    assert len(large) == len(small)
