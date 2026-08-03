from datetime import timedelta
from http import HTTPStatus

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from .models import Application
from .models import Event

User = get_user_model()
MAX_DASHBOARD_QUERIES = 6


class ApplicationActionTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="application-user",
            is_active=True,
        )
        self.client.force_login(self.user)
        today = timezone.localdate()
        self.event = Event.objects.create(
            title="비동기 신청 테스트",
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

    def test_apply_is_post_only_and_idempotent(self):
        url = reverse(
            "applications:apply_event",
            kwargs={"event_id": self.event.pk},
        )

        assert self.client.get(url).status_code == HTTPStatus.METHOD_NOT_ALLOWED

        response = self.ajax_post(url)
        assert response.status_code == HTTPStatus.OK
        assert response.json()["applied"] is True

        second_response = self.ajax_post(url)
        assert second_response.status_code == HTTPStatus.OK
        assert second_response.json()["applied"] is True
        assert (
            Application.objects.filter(
                event=self.event,
                participant=self.user,
            ).count()
            == 1
        )

    def test_cancel_is_post_only_and_idempotent(self):
        Application.objects.create(
            event=self.event,
            participant=self.user,
        )
        url = reverse(
            "applications:cancel_event",
            kwargs={"event_id": self.event.pk},
        )

        assert self.client.get(url).status_code == HTTPStatus.METHOD_NOT_ALLOWED

        response = self.ajax_post(url)
        assert response.status_code == HTTPStatus.OK
        assert response.json()["applied"] is False
        assert not Application.objects.filter(
            event=self.event,
            participant=self.user,
        ).exists()

        second_response = self.ajax_post(url)
        assert second_response.status_code == HTTPStatus.OK
        assert second_response.json()["applied"] is False

    def test_cancel_is_blocked_after_draw(self):
        application = Application.objects.create(
            event=self.event,
            participant=self.user,
            selected=True,
        )
        url = reverse(
            "applications:cancel_event",
            kwargs={"event_id": self.event.pk},
        )

        response = self.ajax_post(url)

        assert response.status_code == HTTPStatus.CONFLICT
        assert response.json()["ok"] is False
        assert Application.objects.filter(pk=application.pk).exists()

    def test_dashboard_uses_post_forms_without_event_query_growth(self):
        today = timezone.localdate()
        Event.objects.bulk_create(
            [
                Event(
                    title=f"추가 활동 {index}",
                    description="",
                    start_date=today + timedelta(days=7),
                    end_date=today + timedelta(days=14),
                    total_slots=1,
                    male_slots=0,
                    female_slots=0,
                )
                for index in range(12)
            ],
        )

        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(reverse("applications:dashboard"))

        assert response.status_code == HTTPStatus.OK
        self.assertContains(response, 'class="application-action-form"', count=13)
        assert len(queries) <= MAX_DASHBOARD_QUERIES
