from allauth.account.forms import SignupForm
from allauth.socialaccount.forms import SignupForm as SocialSignupForm
from django.contrib.auth import forms as admin_forms
from django.utils.translation import gettext_lazy as _

from .models import User
from django import forms 
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model


User = get_user_model()

class SimpleUserSignupForm(UserCreationForm):
    # UserCreationForm에 없는 필드들을 직접 정의합니다.
    name = forms.CharField(max_length=150, required=True, help_text="이름을 입력하세요.")
    gender = forms.ChoiceField(choices=[('M', '남성'), ('F', '여성')], required=True)

    class Meta(UserCreationForm.Meta):
        # model은 settings.py에 설정된 User 모델을 가져옵니다.
        model = get_user_model()
        # UserCreationForm의 기본 필드('username')에 우리가 추가할 필드를 더해줍니다.
        fields = UserCreationForm.Meta.fields + ('name', 'gender')




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
