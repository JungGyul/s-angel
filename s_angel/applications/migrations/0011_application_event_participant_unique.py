from django.db import migrations
from django.db import models
from django.db.models import Count


def ensure_no_duplicate_applications(apps, schema_editor):
    application = apps.get_model("applications", "Application")
    duplicates = list(
        application.objects.values("event_id", "participant_id")
        .annotate(row_count=Count("id"))
        .filter(row_count__gt=1)
        .order_by("event_id", "participant_id")[:10],
    )
    if duplicates:
        pairs = ", ".join(
            f"event={row['event_id']}/participant={row['participant_id']}"
            for row in duplicates
        )
        message = (
            "중복 신청 데이터가 있어 안전하게 마이그레이션을 중단했습니다. "
            f"운영 데이터를 확인한 뒤 다시 진행하세요: {pairs}"
        )
        raise RuntimeError(message)


class Migration(migrations.Migration):
    dependencies = [
        ("applications", "0010_special_lottery"),
    ]

    operations = [
        migrations.RunPython(
            ensure_no_duplicate_applications,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name="application",
            constraint=models.UniqueConstraint(
                fields=("event", "participant"),
                name="unique_application_event_participant",
            ),
        ),
    ]
