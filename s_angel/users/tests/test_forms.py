"""Module for all Form Tests."""

from django.utils.translation import gettext_lazy as _

from s_angel.users.forms import UserAdminCreationForm
from s_angel.users.models import User


class TestUserAdminCreationForm:
    """
    Test class for all tests related to the UserAdminCreationForm
    """

    def test_username_validation_error_msg(self, user: User):
        """
        Tests UserAdminCreation Form's unique validator functions correctly by testing:
            1) A new user with an existing username cannot be added.
            2) Only 1 error is raised by the UserCreation Form
            3) The desired error message is raised
        """

        # The user already exists,
        # hence cannot be created.
        form = UserAdminCreationForm(
            {
                "username": user.username,
                "password1": user.password,
                "password2": user.password,
            },
        )

        assert not form.is_valid()
        assert len(form.errors) == 1
        assert "username" in form.errors
        assert form.errors["username"][0] == _("This username has already been taken.")



def test_signup_duplicate_username_uses_clear_message(user):
    from s_angel.users.forms import SimpleUserSignupForm
    form = SimpleUserSignupForm({
        'username': user.username, 'name': '새 부원', 'gender': 'F', 'generation': 22,
        'password1': 'new-safe-password-9184', 'password2': 'new-safe-password-9184',
    })
    assert not form.is_valid()
    assert form.errors['username'] == ['이미 사용 중인 아이디입니다.']
