from django.db import models
from django.conf import settings
from django.db.models import Sum, Q

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
class BudgetYear(models.Model):
    year = models.IntegerField("연도(기수)", unique=True)
    is_active = models.BooleanField("현재 활성 기수", default=False)

    class Meta:
        ordering = ['-year']

    def __str__(self):
        return f"{self.year}년도"

class AccountingEvent(models.Model):
    budget_year = models.ForeignKey(BudgetYear, on_delete=models.CASCADE, related_name='events')
    name = models.CharField("행사명", max_length=100)
    date = models.DateField("대표 날짜") # 타임라인 정렬 기준
    description = models.TextField(blank=True, verbose_name="행사 설명")

    def __str__(self):
        return f"[{self.budget_year.year}] {self.name}"

    def get_summary(self):
        """행사 내부 수입/지출 합산 (프로퍼티처럼 사용 가능)"""
        data = self.transactions.aggregate(
            income=Sum('amount', filter=Q(transaction_type='INCOME')),
            expense=Sum('amount', filter=Q(transaction_type='EXPENSE'))
        )
        in_val = data['income'] or 0
        ex_val = data['expense'] or 0
        return {'income': in_val, 'expense': ex_val, 'total': in_val - ex_val}

class Transaction(models.Model):
    TRANSACTION_TYPE = [('INCOME', '수입'), ('EXPENSE', '지출')]
    
    # FK 설정
    budget_year = models.ForeignKey(BudgetYear, on_delete=models.CASCADE, related_name='all_transactions', null=True, blank=True)
    event = models.ForeignKey(AccountingEvent, on_delete=models.CASCADE, null=True, blank=True, related_name='transactions')
    
    date = models.DateField(verbose_name="날짜")
    item_name = models.CharField(max_length=100, verbose_name="항목명")
    amount = models.PositiveIntegerField(verbose_name="금액")
    category = models.CharField(max_length=50, verbose_name="카테고리")
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPE, verbose_name="구분")
    description = models.TextField(blank=True, verbose_name="상세 내용")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.item_name} ({self.amount}원)"
# applications/models.py 수정

class ClubSchedule(models.Model):
    title = models.CharField(max_length=200, verbose_name="일정 제목")
    content = models.TextField(blank=True, verbose_name="상세 내용")
    start_at = models.DateTimeField(verbose_name="시작 일시")
    end_at = models.DateTimeField(verbose_name="종료 일시", null=True, blank=True)
    color = models.CharField(max_length=20, default="#1E3A8A", verbose_name="색상")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title
