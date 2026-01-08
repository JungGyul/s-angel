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
    
    # applications/models.py

class Transaction(models.Model):
    TRANSACTION_TYPE = [
        ('INCOME', '수입'),
        ('EXPENSE', '지출'),
    ]
    
    date = models.DateField(verbose_name="날짜")
    item_name = models.CharField(max_length=100, verbose_name="항목명")
    amount = models.PositiveIntegerField(verbose_name="금액") # 음수 방지를 위해 Positive 사용
    category = models.CharField(max_length=50, verbose_name="카테고리") # 예: 회비, 비품, 간식비 등
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPE, verbose_name="구분")
    description = models.TextField(blank=True, verbose_name="상세 내용")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"[{self.get_transaction_type_display()}] {self.item_name} ({self.amount}원)"
    
        # applications/models.py 에 추가

class ClubSchedule(models.Model):
    title = models.CharField(max_length=200, verbose_name="일정 제목")
    content = models.TextField(blank=True, verbose_name="상세 내용")
    start_date = models.DateField(verbose_name="시작 날짜")
    end_date = models.DateField(verbose_name="종료 날짜", null=True, blank=True)
    color = models.CharField(max_length=20, default="#1E3A8A", verbose_name="색상") # 네이비 기본값
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

