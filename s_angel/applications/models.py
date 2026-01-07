from django.db import models
from django.conf import settings

class Event(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    start_date = models.DateField()
    end_date = models.DateField()
    total_slots = models.PositiveIntegerField()
    male_slots = models.PositiveIntegerField()
    female_slots = models.PositiveIntegerField()
    is_finalized = models.BooleanField(default=False) # 최종 확정 여부 추가

    def __str__(self):
        return self.title

class Application(models.Model):
    participant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    applied_at = models.DateTimeField(auto_now_add=True)
    selected = models.BooleanField(default=False)
    failed_count = models.PositiveIntegerField(default=0)
    weight = models.PositiveIntegerField(default=1)

    def __str__(self):
        return f"{self.participant.username} - {self.event.title} ({'당첨' if self.selected else '탈락'})"

