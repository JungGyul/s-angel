from datetime import timedelta
from http import HTTPStatus

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Application
from .models import Event

User = get_user_model()
PRESERVED_WEIGHT = 5


class EventAdminActionTestCase(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="event-manager",
            is_active=True,
            is_staff=True,
        )
        self.client.force_login(self.staff)
        today = timezone.localdate()
        self.event = Event.objects.create(
            title="일반 추첨 관리 테스트",
            description="",
            start_date=today + timedelta(days=7),
            end_date=today + timedelta(days=14),
            total_slots=1,
            male_slots=0,
            female_slots=0,
        )

    def ajax_post(self, url):
        return self.client.post(
            url,
            HTTP_ACCEPT="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    def test_draw_is_post_only_and_cannot_redraw(self):
        first = User.objects.create_user(username="draw-first", weight=4)
        second = User.objects.create_user(username="draw-second", weight=2)
        Application.objects.create(event=self.event, participant=first)
        Application.objects.create(event=self.event, participant=second)
        url = reverse(
            "applications:draw_event",
            kwargs={"event_id": self.event.pk},
        )

        assert self.client.get(url).status_code == HTTPStatus.METHOD_NOT_ALLOWED

        response = self.ajax_post(url)
        assert response.status_code == HTTPStatus.OK
        assert response.json()["drawn"] is True
        selected_ids = set(
            Application.objects.filter(
                event=self.event,
                selected=True,
            ).values_list("pk", flat=True),
        )
        assert len(selected_ids) == 1

        second_response = self.ajax_post(url)
        assert second_response.status_code == HTTPStatus.OK
        assert (
            set(
                Application.objects.filter(
                    event=self.event,
                    selected=True,
                ).values_list("pk", flat=True),
            )
            == selected_ids
        )

    def test_dashboard_renders_draw_and_delete_as_post_forms(self):
        response = self.client.get(reverse("applications:dashboard"))

        assert response.status_code == HTTPStatus.OK
        self.assertContains(
            response,
            'class="dashboard-event-action-form"',
            count=2,
        )

    def test_delete_is_post_only_and_cascades_undrawn_applications(self):
        participant = User.objects.create_user(username="delete-applicant")
        Application.objects.create(event=self.event, participant=participant)
        url = reverse(
            "applications:delete_event",
            kwargs={"event_id": self.event.pk},
        )

        assert self.client.get(url).status_code == HTTPStatus.METHOD_NOT_ALLOWED

        response = self.ajax_post(url)
        assert response.status_code == HTTPStatus.OK
        assert response.json()["deleted"] is True
        assert not Event.objects.filter(pk=self.event.pk).exists()
        assert not Application.objects.filter(event_id=self.event.pk).exists()

    def test_delete_after_draw_keeps_participant_weight(self):
        participant = User.objects.create_user(username="kept-winner")
        participant.weight = PRESERVED_WEIGHT
        participant.save(update_fields=["weight"])
        application = Application.objects.create(
            event=self.event,
            participant=participant,
            selected=True,
        )
        self.event.is_finalized = True
        self.event.save(update_fields=["is_finalized"])
        url = reverse(
            "applications:delete_event",
            kwargs={"event_id": self.event.pk},
        )

        response = self.ajax_post(url)

        assert response.status_code == HTTPStatus.OK
        assert response.json()["deleted"] is True
        assert not Event.objects.filter(pk=self.event.pk).exists()
        assert not Application.objects.filter(pk=application.pk).exists()
        participant.refresh_from_db()
        assert participant.weight == PRESERVED_WEIGHT
