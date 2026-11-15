"""Validate manual accounting writes before changing the ledger."""
from django import forms

from .models import AccountingEvent, Transaction


class AccountingTransactionForm(forms.ModelForm):
    amount = forms.IntegerField(min_value=0, max_value=2147483647, label='금액')

    class Meta:
        model = Transaction
        fields = ('budget_year', 'event', 'date', 'item_name', 'amount',
                  'category', 'transaction_type', 'description')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['budget_year'].required = True

    def clean(self):
        cleaned = super().clean()
        event = cleaned.get('event')
        year = cleaned.get('budget_year')
        if event and year and event.budget_year_id != year.pk:
            raise forms.ValidationError('행사와 회계 연도가 일치하지 않습니다.')
        return cleaned


class AccountingEventForm(forms.ModelForm):
    class Meta:
        model = AccountingEvent
        fields = ('budget_year', 'name', 'date', 'description')
