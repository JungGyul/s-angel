"""Regression checks for protected special lottery operations."""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from .models import Application, Event, SpecialLotteryGroup


@pytest.fixture
def lottery(db):
    staff = get_user_model().objects.create_user(username="lottery-staff", is_staff=True)
    participant = get_user_model().objects.create_user(username="lottery-member", weight=3)
    group = SpecialLotteryGroup.objects.create(name="Protected group")
    event = Event.objects.create(
        title="Finalized event",
        start_date=timezone.localdate(),
        end_date=timezone.localdate(),
        total_slots=1,
        male_slots=0,
        female_slots=0,
        is_finalized=True,
        special_lottery_group=group,
    )
    application = Application.objects.create(
        event=event, participant=participant, selected=True,
    )
    return staff, participant, group, application


@pytest.mark.django_db
@pytest.mark.parametrize("action", ["draw", "save_roster"])
def test_finalized_event_roster_survives_special_lottery_actions(client, lottery, action):
    staff, participant, group, application = lottery
    client.force_login(staff)
    response = client.post(
        reverse(f"applications:special_lottery_{action}", args=[group.pk]),
        {},
    )
    assert response.status_code == 302
    application.refresh_from_db()
    group.refresh_from_db()
    participant.refresh_from_db()
    assert application.selected
    assert not group.is_drawn
    assert participant.weight == 3


@pytest.mark.django_db
@pytest.mark.parametrize("action", ["draw", "save_roster", "finalize", "delete"])
def test_special_lottery_mutations_require_post(client, lottery, action):
    staff, _, group, _ = lottery
    client.force_login(staff)
    assert client.get(
        reverse(f"applications:special_lottery_{action}", args=[group.pk]),
    ).status_code == 405


@pytest.mark.django_db
def test_special_lottery_staff_access_uses_site_login_and_forbidden(client, lottery):
    _, participant, _, _ = lottery
    url = reverse("applications:special_lottery_list")
    response = client.get(url)
    assert response.status_code == 302
    assert response.url.startswith(reverse("users:main"))
    client.force_login(participant)
    assert client.get(url).status_code == 403
