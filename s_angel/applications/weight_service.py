"""Compute provisional lottery weights without changing confirmed user weights."""
from collections import defaultdict
from datetime import datetime, timezone as datetime_timezone

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Exists, OuterRef, Q

from .models import Application, Event, SpecialLotteryGroup, SpecialLotterySettlement


def calculate_weight_adjustment(*, application_count, selected_count,
                                total_application_count, total_selected_count, current_weight):
    if total_application_count == 0 or total_selected_count == 0:
        return SpecialLotterySettlement.Adjustment.KEEP, current_weight
    personal_rate_side = selected_count * total_application_count
    group_rate_side = total_selected_count * application_count
    if personal_rate_side < group_rate_side:
        return SpecialLotterySettlement.Adjustment.INCREASE, current_weight + 1
    if personal_rate_side > group_rate_side:
        return SpecialLotterySettlement.Adjustment.RESET, 1
    return SpecialLotterySettlement.Adjustment.KEEP, current_weight


def _draw_order_key(drawn_at, source_id, source_type):
    earliest = datetime.min.replace(tzinfo=datetime_timezone.utc)
    return (drawn_at or earliest, source_id, source_type)


@transaction.atomic
def calculate_draw_weights(participants, *, exclude_event_id=None, exclude_group_id=None, before_draw=None):
    """Replay other pending rosters on top of User.weight in draw order.

    Legacy draws lacking a timestamp precede timestamped draws in ID order.
    IDs shared across source types use ordinary events first as a stable tie-break.
    Special-lottery denominators include every application, not just candidates.
    """
    participants = list(participants)
    # Serialize draws and confirmations sharing candidates. Reload after locking so
    # a concurrent confirmation cannot combine old weights with a new roster state.
    locked = {
        user.pk: user.weight
        for user in get_user_model().objects.select_for_update()
        .filter(pk__in={participant.pk for participant in participants}).order_by('pk')
    }
    weights = dict(locked)
    for participant in participants:
        participant.weight = locked[participant.pk]
    if not weights:
        return weights
    selected = Application.objects.filter(event_id=OuterRef('pk'), selected=True)
    events = list(Event.objects.filter(is_finalized=False, special_lottery_group__isnull=True)
                  .annotate(has_selected=Exists(selected))
                  .filter(Q(drawn_at__isnull=False) | Q(has_selected=True))
                  .exclude(pk=exclude_event_id).values('pk', 'drawn_at'))
    groups = list(SpecialLotteryGroup.objects.filter(is_drawn=True, is_finalized=False)
                  .exclude(pk=exclude_group_id).values('pk', 'drawn_at'))
    if before_draw is not None:
        boundary = _draw_order_key(*before_draw)
        events = [event for event in events if _draw_order_key(event['drawn_at'], event['pk'], 0) < boundary]
        groups = [group for group in groups if _draw_order_key(group['drawn_at'], group['pk'], 1) < boundary]
    event_ids = [event['pk'] for event in events]
    group_ids = [group['pk'] for group in groups]
    normal_results = defaultdict(dict)
    group_results = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    group_totals = defaultdict(lambda: [0, 0])
    applications = Application.objects.filter(
        Q(event_id__in=event_ids, participant_id__in=weights)
        | Q(event__special_lottery_group_id__in=group_ids),
    ).values_list('event_id', 'event__special_lottery_group_id', 'participant_id', 'selected')
    for event_id, group_id, participant_id, is_selected in applications:
        if group_id is None:
            normal_results[event_id][participant_id] = is_selected
        else:
            group_totals[group_id][0] += 1
            group_totals[group_id][1] += int(is_selected)
            if participant_id in weights:
                group_results[group_id][participant_id][0] += 1
                group_results[group_id][participant_id][1] += int(is_selected)
    timeline = [(event['drawn_at'], event['pk'], 0) for event in events]
    timeline += [(group['drawn_at'], group['pk'], 1) for group in groups]
    timeline.sort(key=lambda item: _draw_order_key(*item))
    for _, source_id, source_type in timeline:
        if source_type == 0:
            for participant_id, is_selected in normal_results[source_id].items():
                weights[participant_id] = 1 if is_selected else weights[participant_id] + 1
        else:
            total_count, total_selected = group_totals[source_id]
            for participant_id, (application_count, selected_count) in group_results[source_id].items():
                _, weights[participant_id] = calculate_weight_adjustment(
                    application_count=application_count, selected_count=selected_count,
                    total_application_count=total_count, total_selected_count=total_selected,
                    current_weight=weights[participant_id],
                )
    return weights


def attach_review_weights(applications, *, exclude_event_id=None, exclude_group_id=None, before_draw=None):
    applications = list(applications)
    missing = [application for application in applications if application.weight is None]
    weights = calculate_draw_weights(
        [application.participant for application in missing],
        exclude_event_id=exclude_event_id, exclude_group_id=exclude_group_id, before_draw=before_draw,
    ) if missing else {}
    for application in applications:
        application.confirmed_weight = application.participant.weight
        application.draw_weight = (
            application.weight if application.weight is not None else weights[application.participant_id]
        )
    return applications
