from allauth.account.forms import SignupForm
from allauth.socialaccount.forms import SignupForm as SocialSignupForm
from django.contrib.auth import forms as admin_forms
from django.utils.translation import gettext_lazy as _

from .models import User
from django import forms 
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import SetPasswordForm


User = get_user_model()

class CustomSetPasswordForm(SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["new_password1"].widget.attrs.update({
            "placeholder": "새 비밀번호",
            "autocomplete": "new-password",
        })
        self.fields["new_password2"].widget.attrs.update({
            "placeholder": "새 비밀번호 확인",
            "autocomplete": "new-password",
        })

class SimpleUserSignupForm(UserCreationForm):
    # UserCreationForm에 없는 필드들을 직접 정의합니다.
    name = forms.CharField(max_length=150, required=True, help_text="이름을 입력하세요.")
    gender = forms.ChoiceField(choices=[('M', '남성'), ('F', '여성')], required=True)
    generation = forms.IntegerField(min_value=1, required=True, help_text="기수를 입력하세요.")

    class Meta(UserCreationForm.Meta):
        # model은 settings.py에 설정된 User 모델을 가져옵니다.
        model = get_user_model()
        # UserCreationForm의 기본 필드('username')에 우리가 추가할 필드를 더해줍니다.
        fields = UserCreationForm.Meta.fields + ('name', 'gender', 'generation')
        
# users/forms.py 파일 하단에 추가

class PasswordResetVerifyForm(forms.Form):
    username = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '아이디'}))
    name = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '이름'}))
    generation = forms.IntegerField(widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '기수 (숫자만)'}))

    def clean(self):
        cleaned_data = super().clean()
        username = cleaned_data.get("username")
        name = cleaned_data.get("name")
        generation = cleaned_data.get("generation")

        if username and name and generation:
            try:
                # 아이디, 이름, 기수가 모두 일치하는 유저가 있는지 확인
                user = User.objects.get(username=username, name=name, generation=generation)
                cleaned_data['user'] = user
            except User.DoesNotExist:
                raise forms.ValidationError("입력하신 정보와 일치하는 사용자가 없습니다.")
        return cleaned_data

class UserProfileChangeForm(forms.ModelForm):
    class Meta:
        model = get_user_model()
        fields = ['username', 'name', 'gender', 'generation']

        labels = {
            'username': '아이디',
            'name': '이름',
            'gender': '성별',
            'generation': '기수',
        }

class UserAdminChangeForm(admin_forms.UserChangeForm):
    class Meta(admin_forms.UserChangeForm.Meta):  # type: ignore[name-defined]
        model = User


class UserAdminCreationForm(admin_forms.AdminUserCreationForm):  # type: ignore[name-defined]  # django-stubs is missing the class, thats why the error is thrown: typeddjango/django-stubs#2555
    """
    Form for User Creation in the Admin Area.
    To change user signup, see UserSignupForm and UserSocialSignupForm.
    """

    class Meta(admin_forms.UserCreationForm.Meta):  # type: ignore[name-defined]
        model = User
        error_messages = {
            "username": {"unique": _("This username has already been taken.")},
        }


class UserSignupForm(SignupForm):
    """
    Form that will be rendered on a user sign up section/screen.
    Default fields will be added automatically.
    Check UserSocialSignupForm for accounts created from social.
    """


class UserSocialSignupForm(SocialSignupForm):
    """
    Renders the form when user has signed up using social accounts.
    Default fields will be added automatically.
    See UserSignupForm otherwise.
    """
