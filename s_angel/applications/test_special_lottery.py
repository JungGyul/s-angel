# ruff: noqa: PLR2004

from datetime import date
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.db import transaction
from django.test import TestCase
from django.urls import reverse

from .models import Application
from .models import Event
from .models import SpecialLotteryGroup
from .models import SpecialLotterySettlement

User = get_user_model()


class SpecialLotteryTestCase(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="manager",
            is_staff=True,
            is_active=True,
        )
        self.client.force_login(self.staff)

    def create_event(self, title, *, total_slots=1):
        return Event.objects.create(
            title=title,
            description="",
            start_date=date(2026, 8, 10),
            end_date=date(2026, 8, 11),
            total_slots=total_slots,
            male_slots=0,
            female_slots=0,
        )

    def create_group(self, *events, draw_mode=SpecialLotteryGroup.DrawMode.BALANCED):
        group = SpecialLotteryGroup.objects.create(
            name="여름 특별 의전",
            draw_mode=draw_mode,
        )
        for order, event in enumerate(events, start=1):
            event.special_lottery_group = group
            event.special_lottery_order = order
            event.save(
                update_fields=[
                    "special_lottery_group",
                    "special_lottery_order",
                ],
            )
        return group

    def test_create_group_requires_and_connects_multiple_events(self):
        event_one = self.create_event("1일차")
        event_two = self.create_event("2일차")

        response = self.client.post(
            reverse("applications:special_lottery_create"),
            {
                "name": "축제 특별추첨",
                "description": "전체 날짜 일괄 추첨",
                "draw_mode": SpecialLotteryGroup.DrawMode.EQUAL,
                "events": [event_one.pk, event_two.pk],
            },
        )

        group = SpecialLotteryGroup.objects.get(name="축제 특별추첨")
        self.assertRedirects(
            response,
            reverse(
                "applications:special_lottery_review",
                kwargs={"group_id": group.pk},
            ),
        )
        assert list(
            group.events.order_by("special_lottery_order").values_list(
                "pk",
                flat=True,
            ),
        ) == [event_one.pk, event_two.pk]

    def test_batch_draw_allows_same_person_on_multiple_events(self):
        participant = User.objects.create_user(
            username="repeat-winner",
            name="반복 당첨자",
            weight=4,
        )
        event_one = self.create_event("1일차")
        event_two = self.create_event("2일차")
        group = self.create_group(event_one, event_two)
        Application.objects.create(event=event_one, participant=participant)
        Application.objects.create(event=event_two, participant=participant)

        response = self.client.post(
            reverse(
                "applications:special_lottery_draw",
                kwargs={"group_id": group.pk},
            ),
        )

        self.assertRedirects(
            response,
            reverse(
                "applications:special_lottery_review",
                kwargs={"group_id": group.pk},
            ),
        )
        group.refresh_from_db()
        assert group.is_drawn
        assert (
            Application.objects.filter(
                participant=participant,
                selected=True,
            ).count()
            == 2
        )

    def test_finalize_settles_weights_from_application_selection_ratio_once(self):
        reset_user = User.objects.create_user(
            username="reset-user",
            name="초기화",
            weight=5,
        )
        increase_user = User.objects.create_user(
            username="increase-user",
            name="증가",
            weight=2,
        )
        keep_user = User.objects.create_user(
            username="keep-user",
            name="유지",
            weight=4,
        )
        event_one = self.create_event("1일차", total_slots=2)
        event_two = self.create_event("2일차", total_slots=1)
        group = self.create_group(event_one, event_two)
        group.is_drawn = True
        group.save(update_fields=["is_drawn"])

        applications = {}
        for event in (event_one, event_two):
            for participant in (reset_user, increase_user, keep_user):
                applications[(event.pk, participant.pk)] = Application.objects.create(
                    event=event,
                    participant=participant,
                )

        finalize_data = {
            f"event_{event_one.pk}_selected": [
                applications[(event_one.pk, reset_user.pk)].pk,
                applications[(event_one.pk, keep_user.pk)].pk,
            ],
            f"event_{event_two.pk}_selected": [
                applications[(event_two.pk, reset_user.pk)].pk,
            ],
            "roster_submission": "1",
        }
        finalize_url = reverse(
            "applications:special_lottery_finalize",
            kwargs={"group_id": group.pk},
        )

        response = self.client.post(finalize_url, finalize_data)

        self.assertRedirects(
            response,
            reverse(
                "applications:special_lottery_review",
                kwargs={"group_id": group.pk},
            ),
        )
        group.refresh_from_db()
        event_one.refresh_from_db()
        event_two.refresh_from_db()
        reset_user.refresh_from_db()
        increase_user.refresh_from_db()
        keep_user.refresh_from_db()

        assert group.is_finalized
        assert event_one.is_finalized
        assert event_two.is_finalized
        assert reset_user.weight == 1
        assert increase_user.weight == 3
        assert keep_user.weight == 4

        settlements = {
            settlement.participant_id: settlement
            for settlement in SpecialLotterySettlement.objects.filter(group=group)
        }
        assert len(settlements) == 3
        assert (
            settlements[reset_user.pk].adjustment
            == SpecialLotterySettlement.Adjustment.RESET
        )
        assert (
            settlements[increase_user.pk].adjustment
            == SpecialLotterySettlement.Adjustment.INCREASE
        )
        assert (
            settlements[keep_user.pk].adjustment
            == SpecialLotterySettlement.Adjustment.KEEP
        )

        self.client.post(finalize_url, finalize_data)
        increase_user.refresh_from_db()
        assert increase_user.weight == 3
        assert (
            SpecialLotterySettlement.objects.filter(group=group).count() == 3
        )

    def test_normal_event_draw_redirects_grouped_event_to_batch_review(self):
        event_one = self.create_event("1일차")
        event_two = self.create_event("2일차")
        group = self.create_group(event_one, event_two)

        response = self.client.get(
            reverse(
                "applications:draw_event",
                kwargs={"event_id": event_one.pk},
            ),
        )

        self.assertRedirects(
            response,
            reverse(
                "applications:special_lottery_review",
                kwargs={"group_id": group.pk},
            ),
        )

    def test_normal_finalize_updates_weights_only_once(self):
        winner = User.objects.create_user(
            username="normal-winner",
            weight=4,
        )
        loser = User.objects.create_user(
            username="normal-loser",
            weight=2,
        )
        event = self.create_event("일반 추첨")
        winner_application = Application.objects.create(
            event=event,
            participant=winner,
        )
        Application.objects.create(
            event=event,
            participant=loser,
        )
        finalize_url = reverse(
            "applications:finalize_event",
            kwargs={"event_id": event.pk},
        )
        finalize_data = {
            "selected_applicants": [winner_application.pk],
        }

        response = self.client.post(finalize_url, finalize_data)

        self.assertRedirects(
            response,
            reverse("applications:dashboard"),
        )
        event.refresh_from_db()
        winner.refresh_from_db()
        loser.refresh_from_db()
        assert event.is_finalized
        assert winner.weight == 1
        assert loser.weight == 3

        self.client.post(finalize_url, finalize_data)
        winner.refresh_from_db()
        loser.refresh_from_db()
        assert winner.weight == 1
        assert loser.weight == 3
        assert self.client.get(finalize_url).status_code == 405

    def test_special_finalize_rolls_back_every_change_on_error(self):
        participant = User.objects.create_user(
            username="rollback-user",
            weight=4,
        )
        event_one = self.create_event("롤백 1일차")
        event_two = self.create_event("롤백 2일차")
        group = self.create_group(event_one, event_two)
        group.is_drawn = True
        group.save(update_fields=["is_drawn"])
        application_one = Application.objects.create(
            event=event_one,
            participant=participant,
        )
        application_two = Application.objects.create(
            event=event_two,
            participant=participant,
        )
        finalize_url = reverse(
            "applications:special_lottery_finalize",
            kwargs={"group_id": group.pk},
        )
        finalize_data = {
            f"event_{event_one.pk}_selected": [application_one.pk],
            f"event_{event_two.pk}_selected": [application_two.pk],
        }

        with (
            patch.object(
                SpecialLotterySettlement.objects,
                "bulk_create",
                side_effect=RuntimeError("forced settlement failure"),
            ),
            pytest.raises(RuntimeError, match="forced settlement failure"),
        ):
            self.client.post(finalize_url, finalize_data)

        group.refresh_from_db()
        event_one.refresh_from_db()
        event_two.refresh_from_db()
        participant.refresh_from_db()
        application_one.refresh_from_db()
        application_two.refresh_from_db()
        assert group.is_drawn
        assert not group.is_finalized
        assert not event_one.is_finalized
        assert not event_two.is_finalized
        assert participant.weight == 4
        assert not application_one.selected
        assert not application_two.selected
        assert not SpecialLotterySettlement.objects.filter(group=group).exists()

    def test_database_rejects_duplicate_application(self):
        participant = User.objects.create_user(username="single-application")
        event = self.create_event("중복 신청 방지")
        Application.objects.create(
            event=event,
            participant=participant,
        )

        with (
            transaction.atomic(),
            pytest.raises(IntegrityError),
        ):
            Application.objects.create(
                event=event,
                participant=participant,
            )

        assert (
            Application.objects.filter(
                event=event,
                participant=participant,
            ).count()
            == 1
        )
