"""Site access, dashboard contracts and finalized lottery regressions."""
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from .models import AccountingEvent, Application, BudgetYear, Event, Transaction


@pytest.fixture
def member(db):
    return get_user_model().objects.create_user(username='security-member', weight=4)


@pytest.fixture
def staff(db):
    return get_user_model().objects.create_user(username='security-staff', is_staff=True)


@pytest.fixture
def event(db):
    return Event.objects.create(title='Secure event', start_date=timezone.localdate(),
                                end_date=timezone.localdate(), total_slots=1,
                                male_slots=0, female_slots=0)


@pytest.mark.parametrize('name,kwargs', [
    ('approve_user', {'user_id': 1}), ('delete_user', {'user_id': 1}),
    ('reject_user', {'user_id': 1}), ('update_user_weight', {'user_id': 1}),
    ('toggle_accounting_permission', {'user_id': 1}),
    ('accounting_delete', {'pk': 1}), ('accounting_event_delete', {'pk': 1}),
    ('initialize_accounting_data', {}), ('create_budget_year', {}),
    ('delete_schedule', {'pk': 1}),
])
def test_staff_mutations_reject_get(client, staff, name, kwargs):
    client.force_login(staff)
    assert client.get(reverse('applications:' + name, kwargs=kwargs)).status_code == 405


def test_site_staff_policy(client, member):
    url = reverse('applications:admin_page')
    assert client.get(url).url.startswith(reverse('users:main'))
    client.force_login(member)
    assert client.get(url).status_code == 403


@pytest.mark.parametrize('name,args', [('accounting_main', []), ('accounting_year_list', [2026]),
                                      ('accounting_event_detail', [1])])
def test_accounting_deep_links_require_permission(client, member, name, args):
    client.force_login(member)
    assert client.get(reverse('applications:' + name, args=args)).status_code == 403


def test_finalization_is_idempotent_and_review_cannot_change_it(client, staff, member, event):
    client.force_login(staff)
    application = Application.objects.create(event=event, participant=member)
    url = reverse('applications:finalize_event', args=[event.pk])
    client.post(url, {'selected_applicants': [application.pk]})
    member.refresh_from_db()
    assert member.weight == 1
    client.post(url, {'selected_applicants': [application.pk]})
    member.refresh_from_db()
    assert member.weight == 1
    client.post(reverse('applications:review_winners', args=[event.pk]), {})
    application.refresh_from_db()
    assert application.selected


def test_dashboard_additional_context_and_local_date(client, member, event):
    client.force_login(member)
    Application.objects.create(event=event, participant=member)
    with patch('s_angel.applications.views.timezone.localdate', return_value=event.end_date):
        response = client.get(reverse('applications:dashboard'))
    assert response.context['my_weight'] == 4
    item = response.context['event_status_list'][0]
    assert item['applicant_count'] == 1
    assert item['is_open'] is True
    assert response.context['my_applications'][0].selected is False


def test_accounting_summary_uses_annotations_without_per_event_queries(db):
    year = BudgetYear.objects.create(year=2026)
    accounting_event = AccountingEvent.objects.create(budget_year=year, name='Summary', date=timezone.localdate())
    Transaction.objects.create(budget_year=year, event=accounting_event, date=timezone.localdate(),
                               item_name='Income', amount=100, category='Other', transaction_type='INCOME')
    from django.db.models import Q, Sum
    annotated = AccountingEvent.objects.annotate(
        summary_income=Sum('transactions__amount', filter=Q(transactions__transaction_type='INCOME')),
        summary_expense=Sum('transactions__amount', filter=Q(transactions__transaction_type='EXPENSE')),
    ).get(pk=accounting_event.pk)
    with CaptureQueriesContext(connection) as queries:
        assert annotated.get_summary() == {'income': 100, 'expense': 0, 'total': 100}
    assert len(queries) == 0


def test_bad_weight_is_not_a_server_error(client, staff, member):
    client.force_login(staff)
    response = client.post(reverse('applications:update_user_weight', args=[member.pk]), {'weight': 'invalid'})
    assert response.status_code == 302
    member.refresh_from_db()
    assert member.weight == 4


def test_optional_event_slots_are_normalized(db):
    from .forms import EventCreateForm
    form = EventCreateForm({'title': 'Optional slots', 'start_date': timezone.localdate(),
                            'end_date': timezone.localdate(), 'total_slots': 2})
    assert form.is_valid(), form.errors
    saved = form.save()
    assert saved.male_slots == saved.female_slots == 0


def test_invalid_review_does_not_clear_existing_winners(client, staff, member, event):
    client.force_login(staff)
    application = Application.objects.create(event=event, participant=member, selected=True)
    response = client.post(reverse('applications:review_winners', args=[event.pk]),
                           {'selected_applicants': ['invalid']})
    assert response.status_code == 302
    application.refresh_from_db()
    assert application.selected


@pytest.mark.parametrize('action', ['add_schedule', 'update_schedule'])
def test_schedule_mutations_return_saved_event(client, staff, action):
    import json
    from .models import ClubSchedule
    client.force_login(staff)
    args = []
    if action == 'update_schedule':
        schedule = ClubSchedule.objects.create(title='Old', start_at=timezone.now())
        args = [schedule.pk]
    response = client.post(reverse('applications:' + action, args=args),
                           data=json.dumps({'title': ' New event ', 'start': '2026-11-15T10:00:00',
                                            'end': '2026-11-15T09:00:00', 'color': '',
                                            'content': 'Saved content'}), content_type='application/json')
    assert response.status_code == 200
    payload = response.json()
    saved = ClubSchedule.objects.get(pk=payload['id'])
    assert payload['status'] == 'success'
    assert payload['title'] == saved.title == 'New event'
    assert payload['start'] == '2026-11-15T10:00:00+09:00'
    assert payload['end'] is None and saved.end_at is None
    assert payload['color'] == saved.color == '#1E3A8A'
    assert payload['content'] == payload['extendedProps']['content'] == saved.content
    assert payload['allDay'] is False


def test_schedule_response_preserves_valid_end_and_color(client, staff):
    import json
    client.force_login(staff)
    response = client.post(reverse('applications:add_schedule'),
                           data=json.dumps({'start': '2026-11-15T01:00:00Z',
                                            'end': '2026-11-15T02:00:00Z', 'color': '#abcdef'}),
                           content_type='application/json')
    payload = response.json()
    assert payload['start'] == '2026-11-15T10:00:00+09:00'
    assert payload['end'] == '2026-11-15T11:00:00+09:00'
    assert payload['color'] == '#abcdef'


@pytest.mark.parametrize('reason', ['', '  \n  '])
def test_budget_year_requires_reason_without_changing_active_year(client, staff, reason):
    from django.contrib.messages import get_messages
    client.force_login(staff)
    existing = BudgetYear.objects.create(year=2026, is_active=True)
    next_url = reverse('applications:accounting_year_list', args=[existing.year])
    response = client.post(reverse('applications:create_budget_year'),
                           {'year': 2027, 'reason': reason, 'next': next_url})
    assert response.url == next_url
    assert [str(message) for message in get_messages(response.wsgi_request)] == ['생성 사유를 입력해 주십시오.']
    existing.refresh_from_db()
    assert existing.is_active
    assert not BudgetYear.objects.filter(year=2027).exists()


def test_budget_year_records_reason_and_creator_with_safe_redirect(client, staff):
    client.force_login(staff)
    existing = BudgetYear.objects.create(year=2026, is_active=True)
    response = client.post(reverse('applications:create_budget_year'),
                           {'year': 2027, 'reason': '  새 기수 시작  ', 'next': 'https://evil.example/'})
    assert response.url == reverse('applications:accounting_main')
    created = BudgetYear.objects.get(year=2027)
    assert created.reason == '새 기수 시작'
    assert created.created_by == staff
    assert created.created_at is not None
    assert created.is_active
    existing.refresh_from_db()
    assert not existing.is_active


def test_budget_year_reactivation_keeps_original_creation_history(client, staff, member):
    existing = BudgetYear.objects.create(year=2026, reason='Original', created_by=member)
    created_at = existing.created_at
    client.force_login(staff)
    client.post(reverse('applications:create_budget_year'), {'year': 2026, 'reason': '다시 활성화'})
    existing.refresh_from_db()
    assert existing.reason == 'Original'
    assert existing.created_by == member
    assert existing.created_at == created_at
    assert existing.is_active
    member.delete()
    existing.refresh_from_db()
    assert existing.created_by is None


def test_budget_year_reason_in_site_form_and_admin(client, staff):
    from django.contrib import admin
    from django.test import RequestFactory
    year = BudgetYear.objects.create(year=2026)
    client.force_login(staff)
    response = client.get(reverse('applications:accounting_year_list', args=[year.year]))
    assert response.status_code == 200
    assert 'name="reason"' in response.content.decode()
    from html.parser import HTMLParser
    class ReasonFieldParser(HTMLParser):
        required = False
        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == 'textarea' and attrs.get('name') == 'reason':
                self.required = 'required' in attrs
    parser = ReasonFieldParser()
    parser.feed(response.content.decode())
    assert parser.required
    model_admin = admin.site._registry[BudgetYear]
    assert {'reason', 'created_at', 'created_by'} <= set(model_admin.list_display)
    request = RequestFactory().get('/')
    request.user = staff
    assert model_admin.get_form(request).base_fields['reason'].required
