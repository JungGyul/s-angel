from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q

from .models import Event
from .models import SpecialLotteryGroup

class EventCreateForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = ['title', 'description', 'start_date', 'end_date', 'total_slots', 'male_slots', 'female_slots']

        labels = {
            'title': '의전 활동',
            'description': '설명',
            'start_date': '시작 날짜',
            'end_date': '마감 날짜',
            'total_slots': '모집 인원 총합',
            'male_slots': '남성 모집 인원',
            'female_slots': '여성 모집 인원',
        }

        widgets = {
            'start_date': forms.DateInput(attrs={'placeholder': '시작 날짜 (YYYY-MM-DD)', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'placeholder': '마감 날짜 (YYYY-MM-DD)', 'type': 'date'}),
            'male_slots': forms.NumberInput(attrs={'placeholder': '성비 맞추는 용도(필수 아님)'}),
            'female_slots': forms.NumberInput(attrs={'placeholder': '성비 맞추는 용도(필수 아님)'}),
        }

    # 여기 추가!
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['male_slots'].required = False
        self.fields['female_slots'].required = False

class UserInfoUpdateForm(forms.ModelForm):
    class Meta:
        model = get_user_model()
        fields = ['gender', 'generation']
        labels = {
            'gender': '성별',
            'generation': '기수',
        }


class SpecialLotteryGroupForm(forms.ModelForm):
    events = forms.ModelMultipleChoiceField(
        queryset=Event.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        label="함께 추첨할 활동",
        help_text="최종 확정되지 않은 활동을 두 개 이상 선택하세요.",
    )

    class Meta:
        model = SpecialLotteryGroup
        fields = ["name", "description", "draw_mode"]
        labels = {
            "name": "특별추첨명",
            "description": "설명",
            "draw_mode": "임시 추첨 방식",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        eligible_events = Event.objects.filter(is_finalized=False).exclude(
            application__selected=True,
        )
        if self.instance.pk:
            eligible_events = eligible_events.filter(
                Q(special_lottery_group__isnull=True)
                | Q(special_lottery_group=self.instance),
            )
            self.fields["events"].initial = self.instance.events.values_list(
                "pk",
                flat=True,
            )
        else:
            eligible_events = eligible_events.filter(
                special_lottery_group__isnull=True,
            )

        self.fields["events"].queryset = eligible_events.order_by(
            "start_date",
            "id",
        ).distinct()

        for field_name in ("name", "description", "draw_mode"):
            self.fields[field_name].widget.attrs["class"] = "form-control"

    def clean_events(self):
        events = self.cleaned_data["events"]
        if events.count() < 2:
            raise forms.ValidationError(
                "특별추첨에는 활동을 두 개 이상 선택해야 합니다.",
            )
        return events

    def save(self, commit=True):
        group = super().save(commit=commit)
        if not commit:
            return group

        selected_events = list(self.cleaned_data["events"])
        selected_event_ids = [event.pk for event in selected_events]
        group.events.exclude(pk__in=selected_event_ids).update(
            special_lottery_group=None,
            special_lottery_order=0,
        )
        for order, event in enumerate(selected_events, start=1):
            Event.objects.filter(pk=event.pk).update(
                special_lottery_group=group,
                special_lottery_order=order,
            )
        return group
