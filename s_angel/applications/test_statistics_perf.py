import datetime as dt

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from s_angel.applications.models import Application, Event

User = get_user_model()


@pytest.fixture
def staff(client):
    user = User.objects.create_user(username="staff", password="pw", is_staff=True, name="운영")
    client.force_login(user)
    return user


def _make(n_events, n_apps):
    users = [User.objects.create(username=f"u{i}", name=f"부원{i}", gender="M" if i % 2 else "F") for i in range(n_apps)]
    today = dt.date.today()
    for e in range(n_events):
        event = Event.objects.create(title=f"의전{e}", start_date=today, end_date=today, total_slots=2, male_slots=1, female_slots=1)
        Application.objects.bulk_create([Application(event=event, participant=u, selected=i < 2) for i, u in enumerate(users)])


@pytest.mark.django_db
def test_statistics_query_count_is_constant_and_paginated(client, staff, django_assert_max_num_queries):
    _make(25, 10)
    with django_assert_max_num_queries(8):
        response = client.get(reverse("applications:event_statistics"))
    assert response.status_code == 200
    assert len(response.context["event_data"]) == 20
    first = response.context["event_data"][0]
    assert first["total_applications"] == 10
    assert first["male_applications"] == 5 and first["female_applications"] == 5
    assert first["total_selected"] == 2 and first["is_drawn"]
    # rosters are not rendered inline any more
    assert b"<tbody>" not in response.content
    page2 = client.get(reverse("applications:event_statistics") + "?page=2")
    assert len(page2.context["event_data"]) == 5


@pytest.mark.django_db
def test_statistics_roster_fragment(client, staff):
    _make(1, 3)
    event = Event.objects.get()
    response = client.get(reverse("applications:event_statistics_roster", args=[event.id]))
    assert response.status_code == 200
    assert response.content.count(b"<tr") == 4  # header + 3 rows
    assert "당첨".encode() in response.content


@pytest.mark.django_db
def test_statistics_roster_requires_staff(client):
    member = User.objects.create_user(username="m", password="pw")
    client.force_login(member)
    _make(1, 1)
    event = Event.objects.get()
    assert client.get(reverse("applications:event_statistics_roster", args=[event.id])).status_code == 403
