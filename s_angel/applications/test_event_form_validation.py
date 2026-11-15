from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from .forms import EventCreateForm
from .models import Event


def event_data(**overrides):
    data = {
        'title': '모집 검증',
        'start_date': '2027-03-01',
        'end_date': '2027-03-10',
        'total_slots': '3',
        'male_slots': '',
        'female_slots': '',
    }
    return {**data, **overrides}


@pytest.mark.parametrize('overrides,error_field', [
    ({'total_slots': '0'}, 'total_slots'),
    ({'total_slots': '-1'}, 'total_slots'),
    ({'male_slots': '2', 'female_slots': '2'}, '__all__'),
    ({'end_date': '2027-02-28'}, 'end_date'),
])
def test_invalid_event_capacity_and_dates_are_rejected(overrides, error_field):
    form = EventCreateForm(event_data(**overrides))
    assert not form.is_valid()
    assert error_field in form.errors


def test_optional_gender_slots_still_default_to_zero_and_same_day_is_valid():
    form = EventCreateForm(event_data(end_date='2027-03-01'))
    assert form.is_valid(), form.errors
    assert form.cleaned_data['male_slots'] == 0
    assert form.cleaned_data['female_slots'] == 0


def test_gender_quotas_may_fill_total_capacity():
    form = EventCreateForm(event_data(male_slots='1', female_slots='2'))
    assert form.is_valid(), form.errors


@pytest.mark.django_db
@pytest.mark.parametrize('action', ['create_event', 'event_update'])
def test_date_inputs_preserve_submitted_dates_on_validation_failure(client, action):
    staff = get_user_model().objects.create_user(username='event-form-staff', is_staff=True)
    client.force_login(staff)
    args = []
    if action == 'event_update':
        event = Event.objects.create(
            title='기존 의전', start_date=date(2027, 2, 1), end_date=date(2027, 2, 3),
            total_slots=2, male_slots=0, female_slots=0,
        )
        args = [event.pk]
    response = client.post(reverse('applications:' + action, args=args), event_data(title=''))
    assert response.status_code == 200
    assert 'value="2027-03-01"' in response.content.decode()
    assert 'value="2027-03-10"' in response.content.decode()


@pytest.mark.django_db
def test_update_form_initial_date_values_use_iso_format(client):
    staff = get_user_model().objects.create_user(username='event-initial-staff', is_staff=True)
    client.force_login(staff)
    event = Event.objects.create(
        title='기존 의전', start_date=date(2027, 2, 1), end_date=date(2027, 2, 3),
        total_slots=2, male_slots=0, female_slots=0,
    )
    response = client.get(reverse('applications:event_update', args=[event.pk]))
    assert response.status_code == 200
    assert 'value="2027-02-01"' in response.content.decode()
    assert 'value="2027-02-03"' in response.content.decode()
