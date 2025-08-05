from django import forms
from .models import Event
from django.contrib.auth import get_user_model

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
class UserGenderUpdateForm(forms.ModelForm):
    class Meta:
        model = get_user_model()
        fields = ['gender']
        labels = {
            'gender': '성별',
        }