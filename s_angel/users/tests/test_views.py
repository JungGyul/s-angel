from http import HTTPStatus

import pytest
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from s_angel.users.models import User

pytestmark = pytest.mark.django_db
TEST_PASSWORD = "test-login-password"  # noqa: S105
UPDATED_GENERATION = 22


def test_main_page(client):
    response = client.get(reverse("users:main"))

    assert response.status_code == HTTPStatus.OK


def test_main_login_redirects_to_dashboard(client, user: User):
    user.set_password(TEST_PASSWORD)
    user.is_active = True
    user.save(update_fields=["password", "is_active"])

    response = client.post(
        reverse("users:main"),
        {
            "username": user.username,
            "password": TEST_PASSWORD,
        },
    )

    assertRedirects(
        response,
        reverse("applications:dashboard"),
        fetch_redirect_response=False,
    )


def test_profile_update_requires_login(client):
    response = client.get(reverse("users:profile_update"))

    expected_url = (
        f"{reverse('account_login')}?next={reverse('users:profile_update')}"
    )
    assertRedirects(
        response,
        expected_url,
        fetch_redirect_response=False,
    )


def test_profile_update(client, user: User):
    client.force_login(user)

    response = client.post(
        reverse("users:profile_update"),
        {
            "username": user.username,
            "name": "수정된 이름",
            "gender": "F",
            "generation": UPDATED_GENERATION,
        },
    )

    assertRedirects(
        response,
        reverse("applications:dashboard"),
        fetch_redirect_response=False,
    )
    user.refresh_from_db()
    assert user.name == "수정된 이름"
    assert user.gender == "F"
    assert user.generation == UPDATED_GENERATION
