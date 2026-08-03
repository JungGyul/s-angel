import pytest
from django.urls import resolve
from django.urls import reverse


@pytest.mark.parametrize(
    ("view_name", "path"),
    [
        ("users:main", "/"),
        ("users:signup", "/signup/"),
        ("users:profile_update", "/profile/update/"),
        ("users:password_reset_verify", "/password-reset/"),
        ("users:password_reset_change", "/password-reset/change/"),
    ],
)
def test_user_urls(view_name, path):
    assert reverse(view_name) == path
    assert resolve(path).view_name == view_name
