import time

import pytest
from django.core.cache import cache
from django.test import Client
from django.urls import reverse

from s_angel.users.forms import PasswordResetVerifyForm

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def reset_attempt_cache():
    cache.clear()
    yield
    cache.clear()


def identity(user):
    return {"username": user.username, "name": user.name, "generation": user.generation}


def test_anonymous_identity_verification_authorizes_password_reset(client, user):
    response = client.post(reverse("users:password_reset_verify"), identity(user))
    assert response.url == reverse("users:password_reset_change")
    assert client.session["reset_user_id"] == user.pk
    assert PasswordResetVerifyForm(identity(user)).is_valid()
    response = client.get(reverse("users:password_reset_change"))
    assert response.status_code == 200


def test_incorrect_identity_cannot_authorize_reset(client, user):
    details = identity(user)
    details['name'] = 'incorrect name'
    response = client.post(reverse("users:password_reset_verify"), details)
    assert response.status_code == 200
    assert response.context['form'].non_field_errors()
    assert 'reset_user_id' not in client.session


def test_reset_session_without_timestamp_is_rejected(client, user):
    session = client.session
    session["reset_user_id"] = user.pk
    session.save()
    response = client.get(reverse("users:password_reset_change"))
    assert response.url == reverse("users:password_reset_verify")
    assert "reset_user_id" not in client.session


def test_anonymous_reset_session_expires(client, user):
    client.post(reverse("users:password_reset_verify"), identity(user))
    session = client.session
    session["reset_issued_at"] = time.time() - 601
    session.save()
    response = client.get(reverse("users:password_reset_change"))
    assert response.url == reverse("users:password_reset_verify")
    assert "reset_user_id" not in client.session


def test_anonymous_reset_session_is_consumed(client, user):
    client.post(reverse("users:password_reset_verify"), identity(user))
    response = client.post(reverse("users:password_reset_change"), {
        "new_password1": "brand-new-strong-password-9184",
        "new_password2": "brand-new-strong-password-9184",
    })
    assert response.url == reverse("users:main")
    for key in ('reset_user_id', 'reset_issued_at', 'reset_auth_hash', 'reset_change_attempts'):
        assert key not in client.session
    user.refresh_from_db()
    assert user.check_password("brand-new-strong-password-9184")
    assert client.get(reverse("users:password_reset_change")).url == reverse("users:password_reset_verify")


def test_reset_attempt_limit(client, user):
    for _ in range(5):
        client.post(reverse("users:password_reset_verify"), {"username": "incorrect"})
    response = client.post(reverse("users:password_reset_verify"), identity(user))
    assert response.status_code == 200
    assert "reset_user_id" not in client.session
    cache.clear()  # Expired cache entries allow a new ten-minute window.
    assert client.post(reverse("users:password_reset_verify"), identity(user)).status_code == 302


def test_password_change_attempt_limit(client, user):
    client.post(reverse("users:password_reset_verify"), identity(user))
    for _ in range(5):
        assert client.post(reverse("users:password_reset_change"), {}).status_code == 200
    response = client.post(reverse("users:password_reset_change"), {
        'new_password1': 'brand-new-strong-password-9184',
        'new_password2': 'brand-new-strong-password-9184',
    })
    assert response.url == reverse('users:password_reset_verify')
    assert 'reset_user_id' not in client.session


def test_password_change_invalidates_an_existing_reset_session(client, user):
    client.post(reverse("users:password_reset_verify"), identity(user))
    user.set_password('changed-elsewhere-9184')
    user.save()
    assert client.get(reverse('users:password_reset_change')).url == reverse('users:password_reset_verify')
    assert 'reset_user_id' not in client.session


@pytest.mark.parametrize("next_url", ["https://evil.example/", "//evil.example/"])
def test_login_rejects_external_next(client, user, next_url):
    user.set_password("login-password-9184")
    user.save()
    response = client.post(reverse("users:main"), {
        "username": user.username, "password": "login-password-9184", "next": next_url,
    })
    assert response.url == reverse("applications:dashboard")


def test_login_accepts_local_next(client, user):
    user.set_password("login-password-9184")
    user.save()
    response = client.post(reverse("users:main"), {
        "username": user.username, "password": "login-password-9184",
        "next": reverse("users:profile_update"),
    })
    assert response.url == reverse("users:profile_update")


def test_logged_in_identity_fields_do_not_authorize_password_change(client, user):
    client.force_login(user)
    response = client.post(reverse('users:password_reset_verify'), identity(user))
    assert response.status_code == 200
    assert response.context['form'].errors
    assert 'reset_user_id' not in client.session


@pytest.mark.parametrize('privilege', ['is_staff', 'is_superuser'])
def test_privileged_accounts_cannot_use_identity_reset(client, user, privilege):
    setattr(user, privilege, True)
    user.save(update_fields=[privilege])
    response = client.post(reverse('users:password_reset_verify'), identity(user))
    assert response.status_code == 200
    assert response.context['form'].non_field_errors()
    assert 'reset_user_id' not in client.session


def test_privilege_granted_after_verification_invalidates_reset(client, user):
    client.post(reverse('users:password_reset_verify'), identity(user))
    user.is_staff = True
    user.save(update_fields=['is_staff'])
    assert client.get(reverse('users:password_reset_change')).url == reverse('users:password_reset_verify')
    assert 'reset_user_id' not in client.session


def test_username_limit_survives_new_cookie_and_new_ip(client, user):
    details = identity(user)
    details['name'] = 'incorrect name'
    for index in range(5):
        response = Client().post(reverse('users:password_reset_verify'), details,
                                 REMOTE_ADDR=f'192.0.2.{index + 1}')
        assert response.status_code == 200
    response = Client().post(reverse('users:password_reset_verify'), identity(user),
                             REMOTE_ADDR='192.0.2.100')
    assert response.status_code == 200
    assert '시도 횟수를 초과' in str(response.context['form'].non_field_errors())


def test_ip_limit_survives_new_cookie_and_new_username(client, user):
    for index in range(5):
        Client().post(reverse('users:password_reset_verify'),
                      {'username': f'other-{index}', 'name': 'missing', 'generation': 21},
                      REMOTE_ADDR='192.0.2.1')
    response = Client().post(reverse('users:password_reset_verify'), identity(user),
                             REMOTE_ADDR='192.0.2.1')
    assert response.status_code == 200
    assert '시도 횟수를 초과' in str(response.context['form'].non_field_errors())


def test_reset_limiter_uses_hashed_expiring_cache_keys():
    from unittest.mock import patch
    from s_angel.users.views import _claim_reset_attempt
    with patch('s_angel.users.views.cache.add', return_value=True) as add:
        assert _claim_reset_attempt('username', 'private-username')
    key, value, timeout = add.call_args.args
    assert 'private-username' not in key
    assert key.startswith('password-reset:username:')
    assert len(key.split(':')[2]) == 64
    assert value is True
    assert timeout == 600


def test_password_reset_does_not_overwrite_concurrent_weight(user):
    from s_angel.users.forms import CustomSetPasswordForm
    from s_angel.users.models import User
    form = CustomSetPasswordForm(user, {
        'new_password1': 'new-safe-password-9184', 'new_password2': 'new-safe-password-9184',
    })
    assert form.is_valid(), form.errors
    User.objects.filter(pk=user.pk).update(weight=9)
    form.save()
    user.refresh_from_db()
    assert user.weight == 9
    assert user.check_password('new-safe-password-9184')


def test_ip_limited_requests_do_not_allocate_username_cache_slots(client, monkeypatch):
    from s_angel.users import views
    calls = []
    def denied(scope, value):
        calls.append(scope)
        return False
    monkeypatch.setattr(views, '_claim_reset_attempt', denied)
    response = client.post(reverse('users:password_reset_verify'), {'username': 'random'})
    assert response.status_code == 200
    assert calls == ['ip']


@pytest.mark.parametrize('privilege', [None, 'is_staff', 'is_superuser'])
def test_authenticated_password_change_uses_current_password_and_preserves_login(client, user, privilege):
    if privilege:
        setattr(user, privilege, True)
    user.set_password('current-safe-password-9184')
    user.save()
    client.force_login(user)
    verify_url = reverse('users:password_reset_verify')
    response = client.get(verify_url)
    html = response.content.decode()
    assert 'name="current_password"' in html
    assert 'name="generation"' not in html
    assert reverse('users:profile_update') in html
    response = client.post(verify_url, {'current_password': 'incorrect'})
    assert response.status_code == 200
    assert 'reset_user_id' not in client.session
    response = client.post(verify_url, {'current_password': 'current-safe-password-9184',
                                       'username': 'some-other-account'})
    assert response.url == reverse('users:password_reset_change')
    assert client.session['reset_user_id'] == user.pk
    assert client.session['reset_authenticated_user_id'] == user.pk
    response = client.post(reverse('users:password_reset_change'), {
        'new_password1': 'updated-safe-password-9184', 'new_password2': 'updated-safe-password-9184',
    })
    assert response.url == reverse('users:profile_update')
    assert client.session['_auth_user_id'] == str(user.pk)
    assert 'reset_user_id' not in client.session
    assert 'reset_authenticated_user_id' not in client.session
    user.refresh_from_db()
    assert user.check_password('updated-safe-password-9184')
    assert client.get(reverse('users:profile_update')).status_code == 200


def test_authenticated_password_grant_cannot_be_used_by_another_login(client, user):
    from s_angel.users.tests.factories import UserFactory
    user.set_password('current-safe-password-9184')
    user.save(update_fields=['password'])
    client.force_login(user)
    client.post(reverse('users:password_reset_verify'), {'current_password': 'current-safe-password-9184'})
    grant = {key: value for key, value in client.session.items() if key.startswith('reset_')}
    other_client = Client()
    other_client.force_login(UserFactory())
    session = other_client.session
    session.update(grant)
    session.save()
    response = other_client.get(reverse('users:password_reset_change'))
    assert response.url == reverse('users:password_reset_verify')
    assert 'reset_user_id' not in other_client.session


def test_anonymous_password_grant_cannot_bypass_authenticated_confirmation(client, user):
    client.post(reverse('users:password_reset_verify'), identity(user))
    client.force_login(user)
    response = client.get(reverse('users:password_reset_change'))
    assert response.url == reverse('users:password_reset_verify')
    assert 'reset_user_id' not in client.session


def test_authenticated_confirmation_grant_expires(client, user):
    user.set_password('current-safe-password-9184')
    user.save(update_fields=['password'])
    client.force_login(user)
    client.post(reverse('users:password_reset_verify'), {'current_password': 'current-safe-password-9184'})
    session = client.session
    session['reset_issued_at'] = time.time() - 601
    session.save()
    response = client.get(reverse('users:password_reset_change'))
    assert response.url == reverse('users:password_reset_verify')
    assert 'reset_user_id' not in client.session
