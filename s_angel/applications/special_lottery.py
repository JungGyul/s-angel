import random
from collections import defaultdict

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count
from django.db.models import Prefetch
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import SpecialLotteryGroupForm
from .models import Application
from .models import Event
from .models import SpecialLotteryGroup
from .models import SpecialLotterySettlement

User = get_user_model()
MINIMUM_GROUP_EVENTS = 2


def _ordered_events(group, *, lock=False):
    events = Event.objects.filter(special_lottery_group=group).order_by(
        "special_lottery_order",
        "start_date",
        "id",
    )
    if lock:
        events = events.select_for_update()
    return events


def _effective_draw_weight(application, draw_mode, selected_counts):
    if draw_mode == SpecialLotteryGroup.DrawMode.EQUAL:
        return 1

    base_weight = max(1, application.participant.weight)
    if draw_mode == SpecialLotteryGroup.DrawMode.BALANCED:
        return base_weight / (selected_counts[application.participant_id] + 1)
    return base_weight


def _pick_applications(pool, count, draw_mode, selected_counts):
    working_pool = list(pool)
    winners = []

    for _ in range(min(count, len(working_pool))):
        weights = [
            _effective_draw_weight(application, draw_mode, selected_counts)
            for application in working_pool
        ]
        winner = random.choices(  # noqa: S311 - This is an operational lottery.
            working_pool,
            weights=weights,
            k=1,
        )[0]
        winners.append(winner)
        selected_counts[winner.participant_id] += 1
        working_pool.remove(winner)

    return winners


def _draw_event_applications(event, applications, draw_mode, selected_counts):
    selected = []
    selected_application_ids = set()

    def pick_from(pool, count):
        available = [
            application
            for application in pool
            if application.id not in selected_application_ids
        ]
        picked = _pick_applications(
            available,
            count,
            draw_mode,
            selected_counts,
        )
        selected.extend(picked)
        selected_application_ids.update(application.id for application in picked)

    if event.male_slots or event.female_slots:
        pick_from(
            [
                application
                for application in applications
                if application.participant.gender == "M"
            ],
            event.male_slots,
        )
        pick_from(
            [
                application
                for application in applications
                if application.participant.gender == "F"
            ],
            event.female_slots,
        )

    remaining_slots = max(0, event.total_slots - len(selected))
    pick_from(applications, remaining_slots)
    return selected[: event.total_slots]


def _calculate_weight_adjustment(
    *,
    application_count,
    selected_count,
    total_application_count,
    total_selected_count,
    current_weight,
):
    if total_application_count == 0 or total_selected_count == 0:
        return SpecialLotterySettlement.Adjustment.KEEP, current_weight

    personal_rate_side = selected_count * total_application_count
    group_rate_side = total_selected_count * application_count

    if personal_rate_side < group_rate_side:
        return SpecialLotterySettlement.Adjustment.INCREASE, current_weight + 1
    if personal_rate_side > group_rate_side:
        return SpecialLotterySettlement.Adjustment.RESET, 1
    return SpecialLotterySettlement.Adjustment.KEEP, current_weight


def _build_review_context(group):
    application_queryset = Application.objects.select_related(
        "participant",
    ).order_by(
        "participant__name",
        "participant__username",
    )
    events = list(
        _ordered_events(group).prefetch_related(
            Prefetch("application_set", queryset=application_queryset),
        ),
    )

    event_rows = []
    participant_stats = {}
    total_application_count = 0
    total_selected_count = 0

    for event in events:
        applications = list(event.application_set.all())
        selected_count = sum(application.selected for application in applications)
        event_rows.append(
            {
                "event": event,
                "applications": applications,
                "selected_count": selected_count,
            },
        )
        total_application_count += len(applications)
        total_selected_count += selected_count

        for application in applications:
            participant = application.participant
            stats = participant_stats.setdefault(
                participant.pk,
                {
                    "participant": participant,
                    "application_count": 0,
                    "selected_count": 0,
                },
            )
            stats["application_count"] += 1
            stats["selected_count"] += int(application.selected)

    settlements = {
        settlement.participant_id: settlement
        for settlement in group.settlements.select_related("participant")
    }

    user_stats = []
    for stats in participant_stats.values():
        participant = stats["participant"]
        settlement = settlements.get(participant.pk)
        if settlement:
            adjustment = settlement.adjustment
            old_weight = settlement.previous_weight
            new_weight = settlement.new_weight
        else:
            adjustment, new_weight = _calculate_weight_adjustment(
                application_count=stats["application_count"],
                selected_count=stats["selected_count"],
                total_application_count=total_application_count,
                total_selected_count=total_selected_count,
                current_weight=participant.weight,
            )
            old_weight = participant.weight

        stats.update(
            {
                "selection_rate": (
                    stats["selected_count"] / stats["application_count"] * 100
                ),
                "old_weight": old_weight,
                "new_weight": new_weight,
                "adjustment": adjustment,
            },
        )
        user_stats.append(stats)

    user_stats.sort(
        key=lambda stats: (
            stats["participant"].name or stats["participant"].username,
            stats["participant"].username,
        ),
    )

    return {
        "group": group,
        "event_rows": event_rows,
        "user_stats": user_stats,
        "total_application_count": total_application_count,
        "total_selected_count": total_selected_count,
        "total_selection_rate": (
            total_selected_count / total_application_count * 100
            if total_application_count
            else 0
        ),
    }


def _parse_roster_from_post(request, events):
    roster = {}
    for event in events:
        field_name = f"event_{event.pk}_selected"
        try:
            selected_ids = {
                int(application_id)
                for application_id in request.POST.getlist(field_name)
            }
        except (TypeError, ValueError):
            return None

        valid_ids = set(
            Application.objects.filter(
                event=event,
                id__in=selected_ids,
            ).values_list("id", flat=True),
        )
        if valid_ids != selected_ids:
            return None
        roster[event.pk] = valid_ids

    return roster


def _save_roster(roster):
    for event_id, selected_ids in roster.items():
        Application.objects.filter(event_id=event_id).update(selected=False)
        if selected_ids:
            Application.objects.filter(
                event_id=event_id,
                id__in=selected_ids,
            ).update(selected=True)


def _roster_mismatch_messages(events):
    mismatches = []
    for event in events:
        selected_count = Application.objects.filter(
            event=event,
            selected=True,
        ).count()
        if selected_count != event.total_slots:
            mismatches.append(
                f"{event.title}: 목표 {event.total_slots}명 / 현재 {selected_count}명",
            )
    return mismatches


@staff_member_required
def special_lottery_list(request):
    groups = SpecialLotteryGroup.objects.prefetch_related("events").all()
    return render(
        request,
        "applications/special_lottery_list.html",
        {"groups": groups},
    )


@staff_member_required
def special_lottery_create(request):
    if request.method == "POST":
        form = SpecialLotteryGroupForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                group = form.save()
            messages.success(
                request,
                f"'{group.name}' 특별추첨 묶음을 만들었습니다.",
            )
            return redirect(
                "applications:special_lottery_review",
                group_id=group.pk,
            )
    else:
        form = SpecialLotteryGroupForm()

    return render(
        request,
        "applications/special_lottery_form.html",
        {"form": form, "page_title": "특별추첨 만들기"},
    )


@staff_member_required
def special_lottery_update(request, group_id):
    group = get_object_or_404(SpecialLotteryGroup, pk=group_id)
    if group.is_drawn or group.is_finalized:
        messages.error(
            request,
            "임시 추첨을 시작한 특별추첨의 구성은 변경할 수 없습니다.",
        )
        return redirect(
            "applications:special_lottery_review",
            group_id=group.pk,
        )

    if request.method == "POST":
        form = SpecialLotteryGroupForm(request.POST, instance=group)
        if form.is_valid():
            with transaction.atomic():
                form.save()
            messages.success(request, "특별추첨 설정을 저장했습니다.")
            return redirect(
                "applications:special_lottery_review",
                group_id=group.pk,
            )
    else:
        form = SpecialLotteryGroupForm(instance=group)

    return render(
        request,
        "applications/special_lottery_form.html",
        {
            "form": form,
            "group": group,
            "page_title": "특별추첨 수정",
        },
    )


@staff_member_required
def special_lottery_review(request, group_id):
    group = get_object_or_404(SpecialLotteryGroup, pk=group_id)
    return render(
        request,
        "applications/special_lottery_review.html",
        _build_review_context(group),
    )


@staff_member_required
@require_POST
def special_lottery_draw(request, group_id):
    with transaction.atomic():
        group = get_object_or_404(
            SpecialLotteryGroup.objects.select_for_update(),
            pk=group_id,
        )
        if group.is_finalized:
            messages.error(request, "이미 최종 확정된 특별추첨입니다.")
            return redirect(
                "applications:special_lottery_review",
                group_id=group.pk,
            )

        events = list(_ordered_events(group, lock=True))
        if len(events) < MINIMUM_GROUP_EVENTS:
            messages.error(request, "활동을 두 개 이상 연결해야 추첨할 수 있습니다.")
            return redirect(
                "applications:special_lottery_review",
                group_id=group.pk,
            )

        invalid_events = [
            event.title
            for event in events
            if event.male_slots + event.female_slots > event.total_slots
        ]
        if invalid_events:
            messages.error(
                request,
                "남성·여성 모집 인원의 합이 전체 모집 인원보다 큰 활동이 있습니다: "
                + ", ".join(invalid_events),
            )
            return redirect(
                "applications:special_lottery_review",
                group_id=group.pk,
            )

        Application.objects.filter(event__in=events).update(selected=False)
        selected_counts = defaultdict(int)
        total_winners = 0

        for event in events:
            applications = list(
                Application.objects.filter(event=event).select_related(
                    "participant",
                ),
            )
            winners = _draw_event_applications(
                event,
                applications,
                group.draw_mode,
                selected_counts,
            )
            winner_ids = [winner.pk for winner in winners]
            if winner_ids:
                Application.objects.filter(pk__in=winner_ids).update(selected=True)
            total_winners += len(winner_ids)

        group.is_drawn = True
        group.save(update_fields=["is_drawn"])

    if total_winners:
        messages.success(
            request,
            f"전체 활동에서 {total_winners}개의 임시 자리를 추첨했습니다.",
        )
    else:
        messages.warning(request, "신청자가 없어 빈 명단으로 저장했습니다.")
    return redirect(
        "applications:special_lottery_review",
        group_id=group.pk,
    )


@staff_member_required
@require_POST
def special_lottery_save_roster(request, group_id):
    with transaction.atomic():
        group = get_object_or_404(
            SpecialLotteryGroup.objects.select_for_update(),
            pk=group_id,
        )
        if group.is_finalized:
            messages.error(request, "최종 확정된 명단은 변경할 수 없습니다.")
            return redirect(
                "applications:special_lottery_review",
                group_id=group.pk,
            )

        events = list(_ordered_events(group, lock=True))
        roster = _parse_roster_from_post(request, events)
        if roster is None:
            messages.error(request, "명단에 잘못된 신청 정보가 포함되어 있습니다.")
            return redirect(
                "applications:special_lottery_review",
                group_id=group.pk,
            )

        _save_roster(roster)
        group.is_drawn = True
        group.save(update_fields=["is_drawn"])
        mismatches = _roster_mismatch_messages(events)

    if mismatches:
        messages.warning(
            request,
            "명단을 저장했습니다. 모집 인원과 다른 활동: " + " / ".join(mismatches),
        )
    else:
        messages.success(request, "특별추첨 명단을 임시 저장했습니다.")
    return redirect(
        "applications:special_lottery_review",
        group_id=group.pk,
    )


@staff_member_required
@require_POST
def special_lottery_finalize(request, group_id):  # noqa: PLR0911
    with transaction.atomic():
        group = get_object_or_404(
            SpecialLotteryGroup.objects.select_for_update(),
            pk=group_id,
        )
        if group.is_finalized:
            messages.warning(request, "이미 최종 확정된 특별추첨입니다.")
            return redirect(
                "applications:special_lottery_review",
                group_id=group.pk,
            )

        events = list(_ordered_events(group, lock=True))
        if not group.is_drawn:
            messages.error(request, "먼저 임시 추첨 또는 명단 저장을 진행해주세요.")
            return redirect(
                "applications:special_lottery_review",
                group_id=group.pk,
            )
        if any(event.is_finalized for event in events):
            messages.error(
                request,
                "묶음 안에 이미 개별 확정된 활동이 있어 특별추첨을 확정할 수 없습니다.",
            )
            return redirect(
                "applications:special_lottery_review",
                group_id=group.pk,
            )
        if group.settlements.exists():
            messages.error(
                request,
                "이미 가중치 정산 이력이 있어 다시 확정할 수 없습니다.",
            )
            return redirect(
                "applications:special_lottery_review",
                group_id=group.pk,
            )

        roster = _parse_roster_from_post(request, events)
        if roster is None:
            messages.error(request, "명단에 잘못된 신청 정보가 포함되어 있습니다.")
            return redirect(
                "applications:special_lottery_review",
                group_id=group.pk,
            )

        applications = Application.objects.filter(event__in=events)
        total_application_count = applications.count()
        total_selected_count = sum(
            len(selected_ids) for selected_ids in roster.values()
        )
        if total_application_count == 0 or total_selected_count == 0:
            messages.error(
                request,
                "신청자와 최종 선발자가 최소 한 명 이상 있어야 확정할 수 있습니다.",
            )
            return redirect(
                "applications:special_lottery_review",
                group_id=group.pk,
            )

        _save_roster(roster)
        aggregates = list(
            applications.values("participant_id").annotate(
                application_count=Count("id"),
                selected_count=Count("id", filter=Q(selected=True)),
            ),
        )
        participant_ids = [
            aggregate["participant_id"] for aggregate in aggregates
        ]
        participants = {
            participant.pk: participant
            for participant in User.objects.select_for_update().filter(
                pk__in=participant_ids,
            )
        }

        settlements = []
        participants_to_update = []
        for aggregate in aggregates:
            participant = participants[aggregate["participant_id"]]
            previous_weight = participant.weight
            adjustment, new_weight = _calculate_weight_adjustment(
                application_count=aggregate["application_count"],
                selected_count=aggregate["selected_count"],
                total_application_count=total_application_count,
                total_selected_count=total_selected_count,
                current_weight=previous_weight,
            )
            participant.weight = new_weight
            participants_to_update.append(participant)
            settlements.append(
                SpecialLotterySettlement(
                    group=group,
                    participant=participant,
                    application_count=aggregate["application_count"],
                    selected_count=aggregate["selected_count"],
                    total_application_count=total_application_count,
                    total_selected_count=total_selected_count,
                    previous_weight=previous_weight,
                    new_weight=new_weight,
                    adjustment=adjustment,
                ),
            )

        User.objects.bulk_update(participants_to_update, ["weight"])
        SpecialLotterySettlement.objects.bulk_create(settlements)
        Event.objects.filter(pk__in=[event.pk for event in events]).update(
            is_finalized=True,
        )
        group.is_finalized = True
        group.finalized_at = timezone.now()
        group.finalized_by = request.user
        group.save(
            update_fields=["is_finalized", "finalized_at", "finalized_by"],
        )

    messages.success(
        request,
        f"'{group.name}' 특별추첨 명단과 가중치를 최종 확정했습니다.",
    )
    return redirect(
        "applications:special_lottery_review",
        group_id=group.pk,
    )
